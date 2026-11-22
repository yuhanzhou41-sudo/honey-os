"""Persistent salience writes for existing cognitive memories."""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3


_MEMORY_KINDS = {"episode", "fact", "procedural"}
_FIELDS = {
    "personal_relevance", "emotional_valence", "arousal", "user_emphasis",
    "unresolvedness", "sensitivity", "recall_affinity", "mention_sensitivity",
}


def set_memory_salience(
    connection: sqlite3.Connection,
    memory_kind: str,
    memory_id: str,
    **values: float,
) -> dict:
    """Upsert selected salience fields, preserving every unspecified field."""
    if memory_kind not in _MEMORY_KINDS:
        raise ValueError(f"unsupported memory kind: {memory_kind}")
    if not str(memory_id).strip():
        raise ValueError("memory_id is required")
    unknown = set(values) - _FIELDS
    if unknown:
        raise ValueError(f"unsupported salience fields: {', '.join(sorted(unknown))}")
    normalized = {}
    for field, value in values.items():
        number = float(value)
        if not 0 <= number <= 1:
            raise ValueError(f"{field} must be between 0 and 1")
        normalized[field] = number
    columns = ["memory_kind", "memory_id", *normalized, "updated_at"]
    assignments = [f"{field}=excluded.{field}" for field in (*normalized, "updated_at")]
    marks = ",".join("?" for _ in columns)
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        f"""INSERT INTO memory_salience ({','.join(columns)}) VALUES ({marks})
            ON CONFLICT(memory_kind,memory_id) DO UPDATE SET {','.join(assignments)}""",
        (memory_kind, memory_id, *normalized.values(), now),
    )
    row = connection.execute(
        "SELECT * FROM memory_salience WHERE memory_kind=? AND memory_id=?",
        (memory_kind, memory_id),
    ).fetchone()
    return dict(row)
