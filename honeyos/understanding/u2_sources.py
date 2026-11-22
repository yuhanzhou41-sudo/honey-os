"""Permission-first exact-body adapter utilities."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

from .contracts import MemorySourceRef
from .u2_contracts import EvidenceUnit
from .u2_store import UnderstandingStore


def resolve_exact_evidence(*, source: MemorySourceRef, expected_revision: str,
                           ref: str, scope_keys: tuple[str, ...],
                           read_body: Callable[[str, str], str],
                           kind: str = "message") -> EvidenceUnit:
    """Read a minimal body only after current permission/revision checks."""
    if source.revision != expected_revision:
        raise RuntimeError("BLOCKED_SOURCE_REVISION")
    if not source.permits("analysis"):
        raise PermissionError("source is not analysis-allowed")
    if source.kind.value in {"recent_chapter"} and not source.source_message_ids:
        raise ValueError("chapter without original message refs is not evidence")
    body = read_body(source.source_record_id, source.revision)
    if not isinstance(body, str) or not body.strip():
        raise ValueError("source body unavailable")
    return EvidenceUnit(
        ref=ref, source_ref=f"{source.source_system}:{source.source_record_id}",
        revision=source.revision, original_message_refs=tuple(
            f"{source.source_session_id}:{item}" for item in source.source_message_ids),
        event_group_id=source.evidence_group, independence="unknown", role="user",
        kind=kind, occurred_at=source.occurred_at,
        time_precision=source.time_precision.value, scope_keys=scope_keys,
        text=body.strip()[:1200], purposes=frozenset(
            {"analysis", "retrieval"} | ({"chat"} if source.chat_allowed else set())),
    )


def build_continuity_recovery_resolver(*, store: UnderstandingStore,
                                       db_path: Path) -> Callable[[dict], tuple[EvidenceUnit, ...] | None]:
    """Bind saved-response recovery to the live continuity source resolver.

    The job row only carries scope and a source hash, so evidence identity is
    read from the metadata-only ledger written before the model call. Every
    source is re-resolved now: a missing/forgotten row, changed revision, or
    withdrawn analysis permission blocks the whole job instead of applying a
    stale response.
    """
    from .continuity_adapter import ContinuitySourceResolver

    def resolve(row: dict) -> tuple[EvidenceUnit, ...] | None:
        rows = store.load_job_evidence(row["id"])
        if not rows:
            return None
        resolver = ContinuitySourceResolver(
            Path(db_path), owner=row["owner"], lane=row["lane"],
            namespace=row["namespace"],
        )
        units: list[EvidenceUnit] = []
        for item in rows:
            source = resolver(row["owner"], item["source_system"], item["source_record_id"])
            if source is None:
                raise PermissionError("source is unavailable, revoked, or out of scope")
            if source.revision != item["source_revision"]:
                raise RuntimeError("BLOCKED_SOURCE_REVISION")
            if not source.permits("analysis"):
                raise PermissionError("source is not analysis-allowed")
            occurred = item["occurred_at"]
            units.append(EvidenceUnit(
                ref=item["evidence_ref"],
                source_ref=f"{item['source_system']}:{item['source_record_id']}",
                revision=source.revision,
                event_group_id=item["event_group"] or source.evidence_group,
                role="user",
                kind="message",
                # Recovery applies an already-saved response; it must not copy
                # or re-read body text merely to satisfy the DTO.
                text="",
                scope_keys=tuple(json.loads(item["scope_keys"])),
                purposes=frozenset(json.loads(item["purposes"])),
                original_message_refs=tuple(json.loads(item["original_message_refs"])),
                occurred_at=datetime.fromisoformat(occurred) if occurred else None,
            ))
        return tuple(units)

    return resolve


def _run_memory_ids(db_path: Path, *, lane: str, run_id: str) -> tuple[str, ...]:
    """List user-stated structured memories written by one completed run."""
    try:
        uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=0.01) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            rows = db.execute("""
                SELECT id FROM structured_memories
                WHERE lane_key=? AND distillation_run_id=? AND status='active'
                      AND evidence='user_stated'
                ORDER BY created_at,id
            """, (lane, run_id)).fetchall()
        return tuple(str(row["id"]) for row in rows)
    except (OSError, sqlite3.Error):
        return ()


def build_run_body_reader(db_path: Path, *,
                          user_messages: Mapping[int, str]) -> Callable[[str, str], str]:
    """Read only original user text cited by an already-authorized memory.

    The continuity row is a source anchor: its ``source_message_ids`` point at
    the user turns that produced it. Only those turns from the completed batch
    are returned, so the reader cannot widen beyond the producing session.
    """
    def read(record_id: str, _revision: str) -> str:
        uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=0.01) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                "SELECT source_message_ids FROM structured_memories WHERE id=?",
                (record_id,),
            ).fetchone()
        raw_ids = row[0] if row is not None else "[]"
        try:
            cited = tuple(int(value) for value in json.loads(raw_ids or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            cited = ()
        parts = [user_messages[item] for item in cited if item in user_messages]
        if not parts:
            raise ValueError("source body unavailable")
        return "\n".join(parts)

    return read


def collect_run_evidence(*, db_path: Path, owner: str, lane: str, namespace: str,
                         run_id: str, session_id: str,
                         user_messages: Mapping[int, str],
                         scope_keys: tuple[str, ...]) -> tuple[EvidenceUnit, ...]:
    """Build live evidence from the memories a completed run just produced.

    Every candidate is re-checked through the formal continuity resolver before
    its body is read. A revoked, expired, revised, or out-of-session source is
    excluded instead of being proposed; chapters are never used as evidence.
    """
    if not scope_keys:
        raise ValueError("controlled scope is required")
    from .continuity_adapter import ContinuitySourceResolver

    resolver = ContinuitySourceResolver(Path(db_path), owner=owner, lane=lane,
                                        namespace=namespace)
    read_body = build_run_body_reader(db_path, user_messages=user_messages)
    units: list[EvidenceUnit] = []
    for record_id in _run_memory_ids(db_path, lane=lane, run_id=run_id):
        source = resolver(owner, "honeyos_structured", record_id)
        if source is None or source.source_session_id != session_id:
            continue
        if not set(source.source_message_ids).intersection(user_messages):
            continue
        try:
            unit = resolve_exact_evidence(
                source=source, expected_revision=source.revision,
                ref=f"honeyos_structured:{record_id}", scope_keys=scope_keys,
                read_body=read_body,
            )
        except (PermissionError, RuntimeError, ValueError):
            continue
        units.append(unit)
    return tuple(units)

