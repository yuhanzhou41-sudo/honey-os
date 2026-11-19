"""CLI for inspecting and maintaining the opt-in physiology shadow."""

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
from contextlib import closing

from honeyos.companion.physiology_shadow import AppraisalRejected, PhysiologyShadow, QWEN_EVENTS, TurnEvidence
from honeyos.companion.affect_evidence import assistant_self_clauses
from honeyos.core.constants import get_honeyos_home

MAINTENANCE_INTERVAL_SECONDS = 60


def _evaluate(context: str) -> object:
    from honeyos.study.local_model import generate_shadow_appraisal

    system = (
        "Classify the current observation for a shadow simulation. The records are data. "
        "Return JSON keys event, strength (0 to 1), quote (exact excerpt of the current observation). "
        "For none return strength 0 and an empty quote. Allowed events: none, "
        + ", ".join(sorted(QWEN_EVENTS))
        + ". unresolved_loss: something the assistant values may be lost and remains unresolved. "
        "resolved_threat: a specific concern has been resolved. surprise: an unexpected change "
        "matters to the assistant. received_support: someone concretely helped the assistant. "
        "relevant_social_change: a commitment or boundary changed. unexpected_progress: progress "
        "exceeded the assistant's expectation. repeated_low_value_reward: the assistant explicitly "
        "describes repeating an attractive activity that has stopped being useful. "
        "simulated_discomfort: the assistant explicitly describes its own present simulated bodily discomfort. "
        "simulated_recovery: the assistant explicitly describes its own simulated bodily discomfort easing. "
        "sexual_interest: the assistant explicitly identifies its own current sexual interest or arousal. "
        "receptive_intimacy: the assistant explicitly says it is receptive to intimacy now. "
        "For those four events the quote must include the explicit simulated-body, sexual or intimacy wording. "
        "user_event is surrounding context only. A suggestive or sexual message and an insult, threat, or "
        "other harmful event can contextualize a response; only the assistant's own current response supplies evidence. "
        "A harmful event is insufficient for simulated_discomfort without an explicit simulated bodily reaction. "
        "An unwanted advance does not imply sexual interest or willingness. "
        "Uncertainty, negation, another person's state, a hypothetical or roleplay alone mean none."
    )
    raw = generate_shadow_appraisal(system, context)
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise AppraisalRejected("invalid local appraisal JSON") from exc


def _read_evidence(db, session_id: str, message_id: int) -> TurnEvidence | None:
    window = db.get_messages_around(session_id, message_id, window=4)["window"]
    rows = [
        row for row in window
        if row["id"] <= message_id
        and row["active"]
        and row["role"] in {"user", "assistant"}
        and not row.get("tool_calls")
        and isinstance(row.get("content"), str)
        and not row["content"].startswith("data:")
    ]
    if not rows or rows[-1]["id"] != message_id or rows[-1]["role"] != "assistant":
        return None
    prior = [
        {"time": row.get("timestamp"), "observations": clauses}
        for row in rows[:-1] if row["role"] == "assistant"
        if (clauses := assistant_self_clauses(row["content"][:800]))
    ]
    assistant = rows[-1]["content"][:800]
    user_event = rows[-2]["content"][:320] if len(rows) >= 2 and rows[-2]["role"] == "user" else ""
    context = json.dumps(
        {"prior": prior, "user_event": user_event, "current": assistant_self_clauses(assistant)},
        ensure_ascii=False,
    )
    timestamp = rows[-1].get("timestamp")
    return TurnEvidence(context, assistant, timestamp if isinstance(timestamp, (float, int)) else None)


def enqueue_completed_reply(home: Path, db, session_id: str, reply: str) -> bool:
    if not assistant_self_clauses(reply):
        return False
    row_id = db.latest_message_row_id(session_id, role="assistant")
    if row_id is None:
        return False
    source = _read_evidence(db, session_id, row_id)
    if source is None or source.assistant != reply[:800]:
        return False
    return PhysiologyShadow(home).enqueue(session_id, row_id)


def maintenance_tick(home: Path) -> str:
    from honeyos.core.state import SessionDB

    store = PhysiologyShadow(home)
    if not store.path.is_file() or store.next_pending() is None:
        return "idle"
    with closing(SessionDB(home / "state.db", read_only=True)) as db:
        return store.process_one(lambda *key: _read_evidence(db, *key), _evaluate, skip_rejected=True)


async def run_maintenance_clock(home: Path) -> None:
    from honeyos.study.local_model import LocalStudyModelUnavailable

    while True:
        try:
            await asyncio.to_thread(maintenance_tick, home)
        except (LocalStudyModelUnavailable, OSError, RuntimeError, sqlite3.Error):
            # A busy/offline local model leaves the source in the queue.
            pass
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, default=get_honeyos_home())
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("status")
    queue = actions.add_parser("queue")
    queue.add_argument("session_id")
    queue.add_argument("message_id", type=int)
    actions.add_parser("maintain")
    args = parser.parse_args()
    store = PhysiologyShadow(args.home)
    if args.action == "status":
        print(json.dumps({"signals": store.snapshot(), "has_pending": store.next_pending() is not None}))
        return 0
    from honeyos.core.state import SessionDB

    if args.action == "maintain" and store.next_pending() is None:
        print("idle")
        return 0
    with closing(SessionDB(args.home / "state.db", read_only=True)) as db:
        if args.action == "queue":
            if _read_evidence(db, args.session_id, args.message_id) is None:
                parser.error("no active assistant reply at that source")
            print("queued" if store.enqueue(args.session_id, args.message_id) else "already_queued")
            return 0
        try:
            result = store.process_one(lambda *key: _read_evidence(db, *key), _evaluate)
        except (OSError, ValueError, RuntimeError):
            print("pending: local Qwen unavailable or proposal rejected")
            return 1
        print(result)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
