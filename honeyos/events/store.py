"""SQLite event ledger for trusted local callers in one HoneyOS profile.

The caller supplies the authenticated principal, never an event payload.
Raw content stays in the originating stores. This broker authorizes access
to event metadata only.
"""

from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

UTC = timezone.utc


class Source(str, Enum):
    CHAT = "chat"
    STUDY = "study"
    REMINDER = "reminder"


class Mode(str, Enum):
    READ = "read"
    WRITE = "write"
    SIDE_EFFECT = "side_effect"
    BACKGROUND = "background"


def _utc(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("Event and grant timestamps must include a timezone")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class Event:
    source: Source
    source_ref: tuple[str, ...]
    kind: str
    occurred_at: datetime

    def fields(self) -> tuple[str, str, str, str]:
        return self.source.value, json.dumps(self.source_ref), self.kind, _utc(self.occurred_at)

    @property
    def id(self) -> str:
        return sha256(json.dumps(self.fields()).encode("utf-8")).hexdigest()


class EventLedger:
    def __init__(self, path, *, clock=lambda: datetime.now(UTC)):
        self.path = path
        self.clock = clock
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, source_ref TEXT NOT NULL,
                    kind TEXT NOT NULL, occurred_at TEXT NOT NULL, observed_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_source_ref ON events(source, source_ref);
                CREATE TABLE IF NOT EXISTS withdrawn_sources (
                    source TEXT NOT NULL, source_ref TEXT NOT NULL, withdrawn_at TEXT NOT NULL,
                    PRIMARY KEY (source, source_ref)
                );
                CREATE TABLE IF NOT EXISTS grants (
                    id TEXT PRIMARY KEY, subject TEXT NOT NULL, app_id TEXT NOT NULL,
                    source TEXT NOT NULL, mode TEXT NOT NULL, expires_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS grants_lookup
                    ON grants(subject, app_id, source, mode, expires_at);
                CREATE TABLE IF NOT EXISTS access_audit (
                    id INTEGER PRIMARY KEY, checked_at TEXT NOT NULL,
                    subject TEXT NOT NULL, app_id TEXT NOT NULL, source TEXT NOT NULL,
                    mode TEXT NOT NULL, grant_id TEXT
                );
            """)

    @contextmanager
    def _transaction(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN IMMEDIATE")
            yield db

    def ingest(self, events) -> int:
        """Store trusted internal projections, deduplicating repeat snapshots."""
        with self._transaction() as db:
            return self._ingest(db, events, _utc(self.clock()))

    @staticmethod
    def _ingest(db, events, observed_at):
        inserted = 0
        for event in events:
            fields = event.fields()
            result = db.execute(
                """INSERT INTO events
                   SELECT ?, ?, ?, ?, ?, ?
                   WHERE NOT EXISTS (SELECT 1 FROM withdrawn_sources
                                     WHERE source=? AND source_ref=?)
                   ON CONFLICT(id) DO NOTHING""",
                (event.id, *fields, observed_at, *fields[:2]),
            )
            inserted += result.rowcount
        return inserted

    def withdraw(self, source: Source, source_ref: tuple[str, ...]):
        """Suppress access and future ingestion while retaining provenance."""
        with self._transaction() as db:
            db.execute(
                "INSERT INTO withdrawn_sources VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
                (source.value, json.dumps(source_ref), _utc(self.clock())),
            )

    def grant(self, subject: str, app_id: str, source: Source, mode: Mode, expires_at: datetime):
        """Record explicit authorization from a trusted control surface."""
        if not subject.strip() or not app_id.strip():
            raise ValueError("Subject and application are required")
        expires = _utc(expires_at)
        grant_id = uuid4().hex
        with self._transaction() as db:
            if expires <= _utc(self.clock()):
                raise ValueError("Grant expiry must be in the future")
            db.execute(
                "INSERT INTO grants VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (grant_id, subject, app_id, source.value, mode.value, expires),
            )
        return grant_id

    def revoke(self, grant_id: str):
        with self._transaction() as db:
            db.execute(
                "UPDATE grants SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
                (_utc(self.clock()), grant_id),
            )

    def revoke_source(self, subject: str, app_id: str, source: Source):
        with self._transaction() as db:
            db.execute(
                """UPDATE grants SET revoked_at=? WHERE subject=? AND app_id=?
                   AND source=? AND mode=? AND revoked_at IS NULL""",
                (_utc(self.clock()), subject, app_id, source.value, Mode.READ.value),
            )

    def review(self, subject: str, app_id: str):
        with self._transaction() as db:
            now = _utc(self.clock())
            grants = db.execute(
                """SELECT source, max(expires_at) AS expires_at FROM grants
                   WHERE subject=? AND app_id=? AND mode=? AND revoked_at IS NULL AND expires_at>?
                   GROUP BY source""",
                (subject, app_id, Mode.READ.value, now),
            )
            audit = db.execute(
                """SELECT source, checked_at, grant_id IS NOT NULL AS allowed FROM access_audit
                   WHERE subject=? AND app_id=? ORDER BY id DESC LIMIT 30""",
                (subject, app_id),
            )
            return {"grants": [dict(row) for row in grants], "audit": [dict(row) for row in audit]}

    def read(
        self, subject: str, app_id: str, source: Source, *, limit: int = 100,
        reference_root: str | None = None, refresh=None,
    ):
        if not 1 <= limit <= 1000:
            raise ValueError("Event limit must be between 1 and 1000")
        with self._transaction() as db:
            now = _utc(self.clock())
            identity = (subject, app_id, source.value, Mode.READ.value)
            grant = db.execute(
                """SELECT id FROM grants WHERE subject=? AND app_id=? AND source=?
                   AND mode=? AND expires_at>? AND revoked_at IS NULL
                   ORDER BY expires_at DESC, id LIMIT 1""",
                (*identity, now),
            ).fetchone()
            db.execute(
                """INSERT INTO access_audit
                   (checked_at, subject, app_id, source, mode, grant_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (now, *identity, grant["id"] if grant else None),
            )
            if grant:
                if refresh is not None:
                    self._ingest(db, refresh(), now)
                return [
                    dict(row) for row in db.execute(
                        """SELECT e.* FROM events e WHERE e.source=?
                           AND (? IS NULL OR json_extract(e.source_ref, '$[0]')=?)
                           AND NOT EXISTS (SELECT 1 FROM withdrawn_sources w
                                           WHERE w.source=e.source AND w.source_ref=e.source_ref)
                           ORDER BY e.occurred_at DESC, e.id LIMIT ?""",
                        (source.value, reference_root, reference_root, limit),
                    )
                ]
        raise PermissionError("No active event read grant")
