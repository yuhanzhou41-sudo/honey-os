"""Explicit SQLite store for U2 labels, evidence, receipts, and postings."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 3


def job_id(owner: str, lane: str, namespace: str, run_id: str,
           source_hash: str, pipeline_version: str) -> str:
    raw = "\0".join((owner, lane, namespace, run_id, source_hash, pipeline_version))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class UnderstandingStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=1.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, lane TEXT NOT NULL,
              namespace TEXT NOT NULL, run_id TEXT NOT NULL, source_hash TEXT NOT NULL,
              pipeline_version TEXT NOT NULL, status TEXT NOT NULL,
              call_issued INTEGER NOT NULL DEFAULT 0 CHECK(call_issued IN(0,1)),
              response_json TEXT, reason TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
              UNIQUE(owner,lane,namespace,run_id,source_hash,pipeline_version));
            CREATE TABLE IF NOT EXISTS labels(
              id TEXT PRIMARY KEY, owner TEXT NOT NULL, lane TEXT NOT NULL,
              namespace TEXT NOT NULL, category TEXT NOT NULL, scope_key TEXT NOT NULL,
              canonical_key TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL,
              grade TEXT NOT NULL, revision INTEGER NOT NULL, policy_epoch INTEGER NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
              UNIQUE(owner,lane,namespace,category,scope_key,canonical_key));
            CREATE TABLE IF NOT EXISTS evidence(
              label_id TEXT NOT NULL REFERENCES labels(id), evidence_ref TEXT NOT NULL,
              event_group TEXT NOT NULL, session_ref TEXT NOT NULL DEFAULT '',
              relation TEXT NOT NULL CHECK(relation IN('support','counter')),
              occurred_at TEXT, source_revision TEXT NOT NULL,
              PRIMARY KEY(label_id,evidence_ref,relation));
            CREATE TABLE IF NOT EXISTS job_evidence(
              job_id TEXT NOT NULL REFERENCES jobs(id),
              evidence_ref TEXT NOT NULL,
              source_system TEXT NOT NULL, source_record_id TEXT NOT NULL,
              source_revision TEXT NOT NULL, event_group TEXT NOT NULL,
              session_ref TEXT NOT NULL DEFAULT '', scope_keys TEXT NOT NULL,
              purposes TEXT NOT NULL, occurred_at TEXT,
              original_message_refs TEXT NOT NULL DEFAULT '[]',
              PRIMARY KEY(job_id,evidence_ref)
            );
            CREATE TABLE IF NOT EXISTS suppressions(
              owner TEXT NOT NULL, lane TEXT NOT NULL, namespace TEXT NOT NULL,
              category TEXT NOT NULL, scope_key TEXT NOT NULL, canonical_hash TEXT NOT NULL,
              active INTEGER NOT NULL DEFAULT 1, policy_epoch INTEGER NOT NULL,
              PRIMARY KEY(owner,lane,namespace,category,scope_key,canonical_hash));
            CREATE TABLE IF NOT EXISTS postings(
              term TEXT NOT NULL, label_id TEXT NOT NULL REFERENCES labels(id),
              owner TEXT NOT NULL, lane TEXT NOT NULL, namespace TEXT NOT NULL,
              PRIMARY KEY(term,label_id));
            CREATE INDEX IF NOT EXISTS ix_postings_scope
              ON postings(owner,lane,namespace,term,label_id);
            CREATE INDEX IF NOT EXISTS ix_evidence_label ON evidence(label_id,relation);
            CREATE TABLE IF NOT EXISTS label_versions(
              label_id TEXT NOT NULL REFERENCES labels(id), revision INTEGER NOT NULL,
              body TEXT NOT NULL, state TEXT NOT NULL, grade TEXT NOT NULL,
              actor TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY(label_id,revision));
            CREATE INDEX IF NOT EXISTS ix_labels_scope_state
              ON labels(owner,lane,namespace,state,updated_at DESC,id);
            CREATE INDEX IF NOT EXISTS ix_labels_scope_updated
              ON labels(owner,lane,namespace,updated_at DESC,id);
            """)
            db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)",
                       (str(SCHEMA_VERSION),))

    def reserve_call(self, *, id: str, owner: str, lane: str, namespace: str,
                     run_id: str, source_hash: str, pipeline_version: str,
                     reason: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute("""INSERT OR IGNORE INTO jobs
                (id,owner,lane,namespace,run_id,source_hash,pipeline_version,status,reason,updated_at)
                VALUES(?,?,?,?,?,?,?,'ready',?,?)""",
                (id, owner, lane, namespace, run_id, source_hash, pipeline_version, reason, now))
            changed = db.execute("""UPDATE jobs SET call_issued=1,status='call_started',updated_at=?
                WHERE id=? AND call_issued=0""", (now, id)).rowcount
            return changed == 1

    def save_response(self, id: str, response_json: str) -> None:
        with self.connect() as db:
            changed = db.execute("""UPDATE jobs SET response_json=?,status='response_saved',updated_at=?
                WHERE id=? AND call_issued=1""",
                (response_json, datetime.now(timezone.utc).isoformat(), id)).rowcount
            if changed != 1:
                raise KeyError(id)

    def save_job_evidence(self, id: str, evidence) -> None:
        """Persist metadata-only evidence identity for restart revalidation.

        No source body is copied. Recovery must resolve each identity against
        the live source store before applying a saved response.
        """
        rows = []
        for item in evidence:
            system, _, record_id = item.source_ref.partition(":")
            if not system or not record_id:
                raise ValueError("evidence source ref must be system:record")
            rows.append((
                id, item.ref, system, record_id, item.revision, item.event_group_id,
                item.original_message_refs[0].split(":", 1)[0] if item.original_message_refs else "",
                json.dumps(list(item.scope_keys), ensure_ascii=False),
                json.dumps(sorted(item.purposes), ensure_ascii=False),
                item.occurred_at.isoformat() if item.occurred_at else None,
                json.dumps(list(item.original_message_refs), ensure_ascii=False),
            ))
        with self.connect() as db:
            db.executemany("""INSERT OR REPLACE INTO job_evidence
                (job_id,evidence_ref,source_system,source_record_id,source_revision,
                 event_group,session_ref,scope_keys,purposes,occurred_at,original_message_refs)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""", rows)

    def load_job_evidence(self, id: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute("""SELECT * FROM job_evidence WHERE job_id=?
                ORDER BY evidence_ref""", (id,)).fetchall()

    def calls_today(self, *, owner: str, lane: str, namespace: str,
                    since: datetime) -> int:
        """Count issued proposal requests inside one explicit window."""
        with self.connect() as db:
            row = db.execute("""SELECT COUNT(*) FROM jobs
                WHERE owner=? AND lane=? AND namespace=? AND call_issued=1
                      AND updated_at>=?""",
                (owner, lane, namespace, since.isoformat())).fetchone()
        return int(row[0])

    def complete(self, id: str) -> None:
        with self.connect() as db:
            changed = db.execute("""UPDATE jobs SET status='completed',updated_at=?
                WHERE id=? AND status IN('response_saved','ready')""",
                (datetime.now(timezone.utc).isoformat(), id)).rowcount
            if changed != 1:
                raise RuntimeError("job is not recoverably complete")

    def bump_policy_epoch(self) -> int:
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key='policy_epoch'").fetchone()
            value = int(row[0]) + 1 if row else 1
            db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('policy_epoch',?)", (str(value),))
            return value

    def policy_epoch(self) -> int:
        with self.connect() as db:
            row = db.execute("SELECT value FROM meta WHERE key='policy_epoch'").fetchone()
            return int(row[0]) if row else 0

    def list_labels(self, owner: str, lane: str, namespace: str, *, limit: int = 100):
        with self.connect() as db:
            return db.execute("""SELECT * FROM labels WHERE owner=? AND lane=? AND namespace=?
                ORDER BY updated_at DESC LIMIT ?""", (owner, lane, namespace, min(limit, 100))).fetchall()

    def page_labels(self, owner: str, lane: str, namespace: str, *,
                    limit: int = 50, offset: int = 0, state: str = "") -> tuple[list, int]:
        """Return one bounded, owner-scoped page without loading the graph."""
        bounded_limit = max(1, min(int(limit), 100))
        bounded_offset = max(0, int(offset))
        where = "owner=? AND lane=? AND namespace=?"
        values: list[object] = [owner, lane, namespace]
        if state:
            where += " AND state=?"
            values.append(state)
        with self.connect() as db:
            total = int(db.execute(f"SELECT COUNT(*) FROM labels WHERE {where}", values).fetchone()[0])
            rows = db.execute(
                f"SELECT * FROM labels WHERE {where} ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",
                (*values, bounded_limit, bounded_offset),
            ).fetchall()
        return list(rows), total

