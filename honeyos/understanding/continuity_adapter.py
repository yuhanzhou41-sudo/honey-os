"""Read-only source resolver for existing companion chapters and cards."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .contracts import MemoryKind, MemorySourceRef

_KINDS = {
    "episode": MemoryKind.EPISODE,
    "open_loop": MemoryKind.OPEN_LOOP,
    "temporary_state": MemoryKind.TEMPORARY_STATE,
    "commitment": MemoryKind.COMMITMENT,
}


class ContinuitySourceResolver:
    """Resolve one source by primary key without opening the source body.

    Owner, lane, and namespace are supplied by the trusted caller because
    continuity.db stores only lane_key. A missing or mismatched row fails closed.
    """

    def __init__(self, db_path: Path, *, owner: str, lane: str,
                 namespace: str = "general"):
        self.db_path = Path(db_path)
        self.owner = owner
        self.lane = lane
        self.namespace = namespace

    def __call__(self, owner: str, system: str, record_id: str) -> MemorySourceRef | None:
        if owner != self.owner or system not in {"honeyos_structured", "honeyos_chapter"}:
            return None
        try:
            uri = self.db_path.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=0.01) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only=ON")
                if system == "honeyos_structured":
                    row = db.execute("""
                        SELECT id,lane_key,kind,status,source_session_id,
                               source_message_ids,created_at,updated_at,expires_at
                        FROM structured_memories WHERE id=? AND lane_key=?
                    """, (record_id, self.lane)).fetchone()
                else:
                    row = db.execute("""
                        SELECT id,lane_key,source_session_id,source_message_ids,
                               source_hash,created_at
                        FROM conversation_chapters WHERE id=? AND lane_key=?
                    """, (record_id, self.lane)).fetchone()
            if row is None:
                return None
            ids = tuple(int(value) for value in json.loads(row["source_message_ids"] or "[]"))
            if system == "honeyos_structured":
                if row["status"] != "active" or row["kind"] not in _KINDS:
                    return None
                expiry = datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
                if expiry and expiry <= datetime.now(timezone.utc):
                    return None
                return MemorySourceRef(
                    source_system=system, source_record_id=row["id"], owner=owner,
                    lane=self.lane, namespace=self.namespace,
                    revision=row["updated_at"], kind=_KINDS[row["kind"]],
                    retrievable=True, chat_allowed=True, analysis_allowed=True,
                    source_session_id=row["source_session_id"], source_message_ids=ids,
                    created_at=datetime.fromisoformat(row["created_at"]), valid_to=expiry,
                )
            return MemorySourceRef(
                source_system=system, source_record_id=row["id"], owner=owner,
                lane=self.lane, namespace=self.namespace,
                revision=f"{row['created_at']}:{row['source_hash']}",
                kind=MemoryKind.RECENT_CHAPTER, retrievable=True,
                chat_allowed=False, analysis_allowed=True,
                source_session_id=row["source_session_id"], source_message_ids=ids,
                source_hash=row["source_hash"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
            return None
