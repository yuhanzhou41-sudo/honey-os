"""Opt-in, metadata-only topic index for the understanding read view.

No source body or model-generated text is stored here. A lookup is useful only
with a live resolver that rechecks the current source revision and permission.
"""

from __future__ import annotations

import sqlite3
import time
import re
import os
from pathlib import Path
from typing import Callable

from .contracts import MemorySourceRef

SCHEMA_VERSION = 1
MAX_LOOKUP = 100
SourceResolver = Callable[[str, str, str], MemorySourceRef | None]


class IndexUnavailable(RuntimeError):
    """The optional index could not be read safely; caller should use legacy flow."""


def _safe_key(value: str) -> str:
    value = str(value or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_.:-]{0,63}", value):
        raise ValueError("index keys must be controlled ASCII identifiers")
    return value


class TopicIndex:
    def __init__(self, path: Path, *, allowed_topics: frozenset[str] = frozenset()):
        self.path = Path(path)
        self.allowed_topics = frozenset(_safe_key(topic) for topic in allowed_topics)

    def _topic(self, topic_id: str) -> str:
        topic = _safe_key(topic_id)
        if topic not in self.allowed_topics:
            raise ValueError("topic is not in the controlled taxonomy")
        return topic

    def initialize(self) -> None:
        """Explicit additive setup; constructing an index never touches disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=1) as db:
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is not None and row[0] != str(SCHEMA_VERSION):
                raise IndexUnavailable("unsupported understanding index version")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    owner TEXT NOT NULL, source_system TEXT NOT NULL,
                    source_record_id TEXT NOT NULL, lane TEXT NOT NULL,
                    namespace TEXT NOT NULL, revision TEXT NOT NULL,
                    evidence_group TEXT NOT NULL,
                    PRIMARY KEY(owner, source_system, source_record_id)
                );
                CREATE TABLE IF NOT EXISTS source_topics (
                    owner TEXT NOT NULL, source_system TEXT NOT NULL,
                    source_record_id TEXT NOT NULL, topic_id TEXT NOT NULL,
                    PRIMARY KEY(owner, source_system, source_record_id, topic_id),
                    FOREIGN KEY(owner, source_system, source_record_id)
                        REFERENCES sources(owner, source_system, source_record_id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_source_topics_lookup
                    ON source_topics(topic_id, owner);
                CREATE TABLE IF NOT EXISTS cursors (
                    owner TEXT NOT NULL, pipeline TEXT NOT NULL,
                    source_batch_id TEXT NOT NULL, pipeline_version TEXT NOT NULL,
                    source_system TEXT NOT NULL, source_record_id TEXT NOT NULL,
                    PRIMARY KEY(owner, pipeline, source_batch_id, pipeline_version,
                                source_system, source_record_id)
                );
            """)
            db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
                       (str(SCHEMA_VERSION),))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def upsert(
        self, source: MemorySourceRef, topic_ids: tuple[str, ...], *,
        source_batch_id: str, pipeline_version: str,
    ) -> bool:
        """Replace one source's topics atomically; return False on exact replay.

        The caller must supply controlled taxonomy IDs, never source text.
        Revision is stored for read-side validation, not interpreted as time.
        """
        if not source.permits("analysis"):
            raise ValueError("source is not authorized for analysis indexing")
        topics = tuple(dict.fromkeys(self._topic(topic) for topic in topic_ids))
        _safe_key(source_batch_id)
        _safe_key(pipeline_version)
        with sqlite3.connect(self.path, timeout=1) as db:
            db.execute("PRAGMA foreign_keys=ON")
            if db.execute(
                "SELECT 1 FROM cursors WHERE owner=? AND pipeline=? AND source_batch_id=? AND pipeline_version=? AND source_system=? AND source_record_id=?",
                (source.owner, "topic_index", source_batch_id, pipeline_version,
                 source.source_system, source.source_record_id),
            ).fetchone():
                return False
            key = (source.owner, source.source_system, source.source_record_id)
            db.execute("""
                INSERT INTO sources(owner,source_system,source_record_id,lane,namespace,revision,evidence_group)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(owner,source_system,source_record_id) DO UPDATE SET
                    lane=excluded.lane, namespace=excluded.namespace,
                    revision=excluded.revision, evidence_group=excluded.evidence_group
            """, (*key, source.lane, source.namespace, source.revision, source.evidence_group))
            db.execute("DELETE FROM source_topics WHERE owner=? AND source_system=? AND source_record_id=?", key)
            db.executemany(
                "INSERT INTO source_topics(owner,source_system,source_record_id,topic_id) VALUES(?,?,?,?)",
                ((*key, topic) for topic in topics),
            )
            db.execute(
                "INSERT INTO cursors(owner,pipeline,source_batch_id,pipeline_version,source_system,source_record_id) VALUES(?,?,?,?,?,?)",
                (source.owner, "topic_index", source_batch_id, pipeline_version,
                 source.source_system, source.source_record_id),
            )
        return True

    def remove(self, *, owner: str, source_system: str, source_record_id: str) -> None:
        """Eager cleanup for explicit deletion; live lookup also fails closed."""
        with sqlite3.connect(self.path, timeout=1) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute(
                "DELETE FROM sources WHERE owner=? AND source_system=? AND source_record_id=?",
                (owner, source_system, source_record_id),
            )

    def lookup(
        self, *, owner: str, lane: str, namespace: str, topic_id: str,
        purpose: str, resolve: SourceResolver, limit: int = 24,
        timeout_ms: int = 30,
    ) -> tuple[MemorySourceRef, ...]:
        """Read bounded headers, then validate every hit against live policy.

        On missing/corrupt/slow index or resolver failure, return no candidates.
        The existing memory path remains responsible for fallback behavior.
        """
        if purpose not in {"retrieval", "analysis", "chat"}:
            return ()
        try:
            topic = self._topic(topic_id)
            amount = min(MAX_LOOKUP, max(1, int(limit)))
            deadline = time.monotonic() + max(1, timeout_ms) / 1000
            uri = self.path.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=0.01) as db:
                db.execute("PRAGMA query_only=ON")
                db.set_progress_handler(lambda: int(time.monotonic() > deadline), 100)
                version = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                if version is None or version[0] != str(SCHEMA_VERSION):
                    raise IndexUnavailable("unsupported understanding index version")
                rows = db.execute("""
                    SELECT s.source_system,s.source_record_id,s.revision
                    FROM source_topics AS t JOIN sources AS s
                    USING(owner,source_system,source_record_id)
                    WHERE t.topic_id=? AND s.owner=? AND s.lane=? AND s.namespace=?
                    ORDER BY s.source_system,s.source_record_id LIMIT ?
                """, (topic, owner, lane, namespace, amount)).fetchall()
            found: list[MemorySourceRef] = []
            groups: set[str] = set()
            for system, record_id, revision in rows:
                if time.monotonic() > deadline:
                    return ()
                source = resolve(owner, system, record_id)
                if time.monotonic() > deadline:
                    return ()
                if source is None or source.revision != revision:
                    continue
                if (source.owner, source.lane, source.namespace, source.source_system,
                    source.source_record_id) != (owner, lane, namespace, system, record_id):
                    continue
                if not source.permits(purpose):
                    continue
                if source.source_session_id and source.source_message_ids:
                    source_groups = {
                        f"message:{source.owner}:{source.source_session_id}:{message_id}"
                        for message_id in source.source_message_ids
                    }
                else:
                    source_groups = {source.evidence_group}
                if source_groups & groups:
                    continue
                groups.update(source_groups)
                found.append(source)
            return tuple(found)
        except Exception:
            return ()
