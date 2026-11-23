"""One-off, bounded U2 evaluation of pre-existing native memories.

This is NOT a backfill service.  It is a single operator-invoked entry point
that reuses the existing U2 proposal contract, store and ``apply_proposal``
write path to evaluate the native memories that no U2 batch has cited yet.
It never re-creates native memories, never runs in the background, never
changes the distillation trigger, and never writes test fixtures into the
production database.

Default mode is a read-only dry run that reports how many memories are
eligible and how many bounded model requests a real run would issue.

    python -m honeyos.understanding.u2_backfill            # dry run
    python -m honeyos.understanding.u2_backfill --execute  # one real run
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .u2_contracts import BatchEnvelope, EvidenceUnit
from .u2_maintenance import _label_id
from .u2_pipeline import build_proposal_call, recover_saved_response, resolve_model_from_runtime
from .u2_proposer import parse_response, propose_once
from .u2_store import UnderstandingStore, job_id

OWNER = "local-owner"
PIPELINE_VERSION = "u2-backfill-v1"
MAX_INPUT_CHARS = 7600
MAX_EVIDENCE_CHARS = 1200
MAX_BATCH_ITEMS = 12


@dataclass(frozen=True, slots=True)
class Candidate:
    memory_id: str
    session_id: str
    text: str
    revision: str
    occurred_at: datetime
    created_at: str

    @property
    def ref(self) -> str:
        return f"continuity:{self.memory_id}"

    def evidence(self, namespace: str) -> EvidenceUnit:
        return EvidenceUnit(
            ref=self.ref,
            source_ref=f"honeyos_structured:{self.memory_id}",
            revision=self.revision,
            event_group_id=self.memory_id,
            role="user",
            kind="message",
            text=self.text[:MAX_EVIDENCE_CHARS],
            scope_keys=(namespace,),
            purposes=frozenset({"analysis", "retrieval"}),
            original_message_refs=(f"{self.session_id}:{self.memory_id}",),
            occurred_at=self.occurred_at,
        )


@dataclass
class Report:
    found: int = 0
    already_processed: int = 0
    ineligible: int = 0
    sent: int = 0
    planned_calls: int = 0
    calls: int = 0
    new_labels: int = 0
    updated_labels: int = 0
    relations: int = 0
    rejected: int = 0
    noop: int = 0
    remaining: int = 0
    provider: str = ""
    model: str = ""
    errors: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        data = dict(self.__dict__)
        data["errors"] = list(self.errors or [])
        return data


def _connect_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True,
                           timeout=1.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _cited_memory_ids(store: UnderstandingStore, *, include_jobs: bool = True) -> set[str]:
    """Continuity memories already cited by U2 evidence (and optionally jobs)."""
    cited: set[str] = set()
    if not Path(store.path).is_file():
        return cited
    try:
        with store.connect() as db:
            tables = [("evidence", "evidence_ref")]
            if include_jobs:
                tables.append(("job_evidence", "evidence_ref"))
            for table, column in tables:
                rows = db.execute(f"SELECT {column} AS ref FROM {table}").fetchall()
                for row in rows:
                    ref = str(row["ref"] or "")
                    for prefix in ("continuity:", "honeyos_structured:"):
                        if ref.startswith(prefix):
                            cited.add(ref.split(":", 1)[1])
    except sqlite3.Error:
        return cited
    return cited


def _user_text(db: sqlite3.Connection, message_ids: Iterable[int],
               session_id: str) -> str:
    """Original user turns cited by one memory; assistant rows never count."""
    parts: list[str] = []
    for raw in message_ids:
        try:
            message_id = int(raw)
        except (TypeError, ValueError):
            continue
        if message_id <= 0:
            continue
        row = db.execute(
            "SELECT role, content, session_id FROM messages WHERE id=?",
            (message_id,),
        ).fetchone()
        if row is None or str(row["role"]) != "user":
            continue
        if str(row["session_id"] or "") != session_id:
            continue
        content = str(row["content"] or "").strip()
        if content:
            parts.append(content)
    return "\n".join(parts)


def collect(home: Path, lane: str, namespace: str, *,
            store: UnderstandingStore) -> tuple[list[Candidate], Report]:
    """Read-only candidate discovery. Never writes to either database."""
    report = Report()
    continuity = home / "continuity.db"
    state = home / "state.db"
    if not continuity.is_file() or not state.is_file():
        report.errors = ["continuity.db or state.db missing"]
        return [], report
    cited = _cited_memory_ids(store)
    now = datetime.now(timezone.utc)
    candidates: list[Candidate] = []
    try:
        memory_db = _connect_ro(continuity)
        message_db = _connect_ro(state)
        try:
            rows = memory_db.execute(
                """SELECT id, lane_key, kind, status, evidence, source_session_id,
                          source_message_ids, created_at, updated_at, expires_at
                   FROM structured_memories
                   WHERE lane_key=? AND status='active'
                     AND kind IN ('episode','commitment') AND evidence='user_stated'
                   ORDER BY created_at, id""",
                (lane,),
            ).fetchall()
        finally:
            pass
        for row in rows:
            report.found += 1
            memory_id = str(row["id"])
            if memory_id in cited:
                report.already_processed += 1
                continue
            expires = str(row["expires_at"] or "")
            if expires:
                try:
                    if datetime.fromisoformat(expires) <= now:
                        report.ineligible += 1
                        continue
                except ValueError:
                    pass
            try:
                message_ids = tuple(int(v) for v in json.loads(
                    row["source_message_ids"] or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                message_ids = ()
            session_id = str(row["source_session_id"] or "")
            text = _user_text(message_db, message_ids, session_id)
            if not text:
                report.ineligible += 1
                continue
            created = datetime.fromisoformat(str(row["created_at"]))
            candidates.append(Candidate(
                memory_id=memory_id,
                session_id=session_id,
                text=text,
                revision=str(row["updated_at"]),
                occurred_at=created,
                created_at=str(row["created_at"]),
            ))
    finally:
        if "memory_db" in locals():
            memory_db.close()
        if "message_db" in locals():
            message_db.close()
    return candidates, report


def _batches(candidates: list[Candidate], namespace: str,
             limit_chars: int) -> list[tuple[EvidenceUnit, ...]]:
    """Greedy bounded grouping under the proposer's input budget."""
    batches: list[tuple[EvidenceUnit, ...]] = []
    current: list[EvidenceUnit] = []
    size = 0
    for candidate in candidates:
        unit = candidate.evidence(namespace)
        payload = json.dumps({"ref": unit.ref, "text": unit.text,
                              "scope_keys": list(unit.scope_keys),
                              "event_group": unit.event_group_id,
                              "occurred_at": unit.occurred_at.isoformat()
                              if unit.occurred_at else None},
                             ensure_ascii=False, separators=(",", ":"))
        if current and (size + len(payload) > limit_chars
                        or len(current) >= MAX_BATCH_ITEMS):
            batches.append(tuple(current))
            current, size = [], 0
        current.append(unit)
        size += len(payload)
    if current:
        batches.append(tuple(current))
    return batches


def _runtime() -> dict[str, Any]:
    from honeyos.companion.distillation import _main_runtime_from_config

    runtime = _main_runtime_from_config()
    return {
        key: value for key, value in runtime.items()
        if isinstance(value, str) and value.strip()
    }


def _label_ids(store: UnderstandingStore) -> set[str]:
    try:
        with store.connect() as db:
            return {str(row[0]) for row in db.execute("SELECT id FROM labels")}
    except sqlite3.Error:
        return set()


def _evidence_count(store: UnderstandingStore) -> int:
    try:
        with store.connect() as db:
            return int(db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0])
    except sqlite3.Error:
        return 0


def run(home: Path, *, lane: str, namespace: str, execute: bool,
        limit_chars: int = MAX_INPUT_CHARS,
        max_daily_calls: int = 6) -> Report:
    home = Path(home)
    store = UnderstandingStore(home / "understanding_v2.db") if execute else None
    if store is not None:
        store.initialize()
    read_store = store or UnderstandingStore(home / "understanding_v2.db")
    candidates, report = collect(home, lane, namespace, store=read_store)
    batches = _batches(candidates, namespace, limit_chars)
    report.sent = len(candidates)
    report.planned_calls = len(batches)
    report.remaining = len(candidates)
    runtime = _runtime()
    report.provider = str(runtime.get("provider") or "")
    report.model = str(runtime.get("model") or "")
    if not execute:
        return report
    if store is None:
        raise RuntimeError("store unavailable")
    if not runtime.get("provider") or not runtime.get("model"):
        report.errors = ["no distillation model runtime configured"]
        return report
    day_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0)
    already_today = store.calls_today(owner=OWNER, lane=lane, namespace=namespace,
                                      since=day_start)
    if already_today >= max(1, int(max_daily_calls)):
        report.errors = [f"daily U2 call budget exhausted ({already_today})"]
        return report

    model = resolve_model_from_runtime(runtime)
    assert model is not None
    call = build_proposal_call(runtime)
    run_id = datetime.now(timezone.utc).strftime("backfill-%Y%m%dT%H%M%S%f")
    for batch in batches:
        reviews = max(1, len(batch))
        source_hash = hashlib.sha256(
            "\0".join(sorted(unit.ref for unit in batch)).encode()
        ).hexdigest()[:32]
        jid = job_id(OWNER, lane, namespace, run_id, source_hash, PIPELINE_VERSION)
        if not store.reserve_call(id=jid, owner=OWNER, lane=lane,
                                  namespace=namespace, run_id=run_id,
                                  source_hash=source_hash,
                                  pipeline_version=PIPELINE_VERSION,
                                  reason="UNATTENDED_HISTORY_REVIEW"):
            report.errors = (report.errors or []) + ["job already issued"]
            continue
        store.save_job_evidence(jid, batch)
        try:
            proposals = asyncio.run(propose_once(
                model=model, evidence=batch, call=call, timeout=120.0,
                max_input_chars=limit_chars,
            ))
            raw = json.dumps({"proposals": [asdict(p) for p in proposals]},
                             ensure_ascii=False, default=list)
            store.save_response(jid, raw)
        except Exception as exc:  # one attempt only, never auto-retried
            report.errors = (report.errors or []) + [
                f"proposal call failed: {type(exc).__name__}: {exc}"
            ]
            report.calls += 1
            continue
        report.calls += 1
        before_ids = _label_ids(store)
        before_evidence = _evidence_count(store)
        try:
            parse_response(raw, allowed_refs={u.ref for u in batch},
                           allowed_scopes={namespace})
            envelope = BatchEnvelope(
                OWNER, lane, namespace, run_id, source_hash, source_hash,
                datetime.now(timezone.utc), PIPELINE_VERSION,
            )
            recover_saved_response(
                envelope=envelope, evidence=batch, store=store,
                response_json=raw, jid=jid,
                continuity_db_path=home / "continuity.db",
            )
        except Exception as exc:
            report.rejected += 1
            report.errors = (report.errors or []) + [
                f"apply failed: {type(exc).__name__}: {exc}"
            ]
            continue
        for proposal in proposals:
            if _label_id(OWNER, lane, namespace, proposal) in before_ids:
                report.updated_labels += 1
            else:
                report.new_labels += 1
        report.relations += max(0, _evidence_count(store) - before_evidence)
        # Every unit in this batch was evaluated by the model, even when the
        # model chose not to cite it (a legal no-op). Only failed calls leave
        # an unprocessed remainder.
        report.remaining = max(0, report.remaining - reviews)
    cited_candidates = _cited_memory_ids(store, include_jobs=False)
    report.noop = sum(
        1 for candidate in candidates if candidate.memory_id not in cited_candidates)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate pre-existing native memories against the U2 contract.")
    parser.add_argument("--execute", action="store_true",
                        help="issue the bounded model call(s) and persist results")
    parser.add_argument("--home", default="", help="HoneyOS home (default: ~/.honeyos)")
    parser.add_argument("--lane", default="agent:main:api_server:dm:local-owner")
    parser.add_argument("--namespace", default="")
    parser.add_argument("--max-chars", type=int, default=MAX_INPUT_CHARS)
    args = parser.parse_args(argv)

    home = Path(args.home).expanduser() if args.home else Path.home() / ".honeyos"
    namespace = args.namespace
    max_calls = 6
    try:
        from honeyos.companion.distillation import load_distillation_settings

        settings = load_distillation_settings(home).understanding
        namespace = namespace or str(getattr(settings, "namespace", "") or "general")
        max_calls = int(getattr(settings, "max_daily_calls", 6) or 6)
    except Exception:
        namespace = namespace or "general"
    report = run(home, lane=args.lane, namespace=namespace, execute=args.execute,
                 limit_chars=args.max_chars, max_daily_calls=max_calls)
    print(json.dumps({"mode": "execute" if args.execute else "dry-run",
                      "namespace": namespace, **report.as_dict()},
                     ensure_ascii=False, indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
