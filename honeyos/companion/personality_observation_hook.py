"""Fail-open runtime observation capture for completed assistant turns."""

from __future__ import annotations

from pathlib import Path
from contextlib import closing
from typing import Any

from honeyos.companion.personality_candidates import PersonalityCandidateStore
from honeyos.companion.personality_observation import detect_observation_signals


def _is_liked(db, session_id: str, message_id: int) -> bool:
    return db.get_message_role(session_id, message_id) == "assistant" and any(
        item.get("author") == "user" and item.get("emoji") == "👍"
        for item in db.get_message_reactions(session_id, message_id)
    )


def capture_liked_reply(home: Path | str, db, session_id: str, message_id: int) -> str:
    if not _is_liked(db, session_id, message_id):
        return ""
    rows = db.get_messages_around(session_id, message_id, window=3)["window"]
    reply = next((row for row in rows if row["id"] == message_id and row["active"]), None)
    if not reply or not isinstance(reply["content"], str) or not reply["content"].strip() or reply.get("tool_calls"):
        return ""
    if reply.get("display_kind") in {"hidden", "auto_continue", "model_switch"}:
        return ""
    user = next((row for row in reversed(rows) if row["id"] < message_id and row["role"] == "user" and row["active"]), None)
    excerpt = user["content"] if user and isinstance(user["content"], str) else ""
    signals = detect_observation_signals(user_text=excerpt, assistant_text=reply["content"])
    return PersonalityCandidateStore(home, liked_only=True).capture_observation(
        session_id=session_id, assistant_reference=f"liked:{message_id}",
        user_reference=f"liked-user:{user['id']}" if user else "",
        user_excerpt=excerpt, assistant_excerpt=reply["content"], signal_flags=signals.flags,
    )


def liked_observation_ids(home: Path | str, rows) -> set[str]:
    from honeyos.core.state import SessionDB

    if not rows:
        return set()
    approved = set()
    with closing(SessionDB(Path(home) / "state.db", read_only=True)) as db:
        for row in rows:
            prefix, _, ref = str(row["assistant_reference"]).partition(":")
            if prefix == "liked" and ref.isascii() and ref.isdecimal() and len(ref) <= 18:
                if _is_liked(db, row["session_id"], int(ref)):
                    approved.add(str(row["observation_id"]))
    return approved


def capture_completed_turn_observation(
    home: Path | str,
    *,
    session_id: str = "",
    user_reference: str = "",
    assistant_reference: str = "",
    user_text: str = "",
    assistant_text: str = "",
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Capture a high-signal completed turn.

    Fail-open: all observation failures are converted to a non-captured result.
    No exception from this helper should break normal chat.
    """

    try:
        signals = detect_observation_signals(
            user_text=user_text,
            assistant_text=assistant_text,
        )
        if not signals.eligible:
            return {
                "captured": False,
                "observation_id": "",
                "signal_flags": [],
                "error": "",
            }

        store = PersonalityCandidateStore(home)
        observation_id = store.capture_observation(
            session_id=session_id,
            user_reference=user_reference,
            assistant_reference=assistant_reference,
            observed_at=observed_at,
            signal_flags=list(signals.flags),
            user_excerpt=user_text,
            assistant_excerpt=assistant_text,
        )
        return {
            "captured": True,
            "observation_id": observation_id,
            "signal_flags": list(signals.flags),
            "error": "",
        }
    except Exception as exc:
        return {
            "captured": False,
            "observation_id": "",
            "signal_flags": [],
            "error": str(exc)[:500],
        }


def _coerce_message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        content = value.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
        return str(content or "")
    return str(value or "")


def _resolve_companion_home(agent: Any) -> Path:
    import os

    configured_home = os.environ.get("HONEYOS_HOME", "").strip()
    if configured_home:
        return Path(configured_home).expanduser()
    agent_home = getattr(agent, "honeyos_home", None)
    return Path(agent_home).expanduser() if agent_home else Path.home() / ".honeyos"


def capture_completed_agent_turn_observation(
    agent: Any,
    *,
    turn_id: str = "",
    user_message: Any = "",
    assistant_response: Any = "",
    observed_at: str | None = None,
) -> dict[str, Any]:
    try:
        home = _resolve_companion_home(agent)

        turn = str(turn_id or "").strip()
        return capture_completed_turn_observation(
            home,
            session_id=str(getattr(agent, "session_id", "") or ""),
            user_reference=f"{turn}:user" if turn else "",
            assistant_reference=f"{turn}:assistant" if turn else "",
            user_text=_coerce_message_text(user_message),
            assistant_text=_coerce_message_text(assistant_response),
            observed_at=observed_at,
        )
    except Exception as exc:
        return {
            "captured": False,
            "observation_id": "",
            "signal_flags": [],
            "error": str(exc)[:500],
        }
