"""Opt-in metadata-only index for bounded personal-fact lookup."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Callable

from .contracts import PersonalFactRef

SCHEMA_VERSION = 1
MAX_LOOKUP = 50
FactResolver = Callable[[str, str, str], PersonalFactRef | None]
_KEY = re.compile(r"[a-z][a-z0-9_.:-]{0,63}\Z")


def _key(value: str) -> str:
    value = str(value or "").strip().lower()
    if not _KEY.fullmatch(value):
        raise ValueError("fact predicates must be controlled ASCII identifiers")
    return value


class PersonalFactIndex:
    def __init__(self, path: Path, *, allowed_predicates: frozenset[str]):
        self.path = Path(path)
        self.allowed_predicates = frozenset(_key(item) for item in allowed_predicates)

    def _predicate(self, value: str) -> str:
        predicate = _key(value)
        if predicate not in self.allowed_predicates:
            raise ValueError("predicate is not in the controlled fact taxonomy")
        return predicate

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=1) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS personal_facts (
                    owner TEXT NOT NULL, source_system TEXT NOT NULL,
                    source_record_id TEXT NOT NULL, lane TEXT NOT NULL,
                    namespace TEXT NOT NULL, predicate TEXT NOT NULL,
                    value_ref TEXT NOT NULL, revision TEXT NOT NULL,
                    authority TEXT NOT NULL, privacy_level TEXT NOT NULL,
                    PRIMARY KEY(owner,source_system,source_record_id)
                );
                CREATE INDEX IF NOT EXISTS idx_personal_facts_lookup
                    ON personal_facts(owner,lane,namespace,predicate);
            """)
            row = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            if row is not None and row[0] != str(SCHEMA_VERSION):
                raise RuntimeError("unsupported personal fact index version")
            db.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
                       (str(SCHEMA_VERSION),))
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def upsert(self, fact: PersonalFactRef) -> None:
        predicate = self._predicate(fact.predicate)
        if not fact.source.permits("analysis"):
            raise ValueError("fact source is not authorized for analysis indexing")
        with sqlite3.connect(self.path, timeout=1) as db:
            db.execute("""
                INSERT INTO personal_facts(
                    owner,source_system,source_record_id,lane,namespace,predicate,
                    value_ref,revision,authority,privacy_level
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(owner,source_system,source_record_id) DO UPDATE SET
                    lane=excluded.lane, namespace=excluded.namespace,
                    predicate=excluded.predicate, value_ref=excluded.value_ref,
                    revision=excluded.revision, authority=excluded.authority,
                    privacy_level=excluded.privacy_level
            """, (
                fact.source.owner, fact.source.source_system,
                fact.source.source_record_id, fact.source.lane,
                fact.source.namespace, predicate, fact.value_ref,
                fact.source.revision, fact.authority.value, fact.privacy_level.value,
            ))

    def remove(self, *, owner: str, source_system: str, source_record_id: str) -> None:
        with sqlite3.connect(self.path, timeout=1) as db:
            db.execute("DELETE FROM personal_facts WHERE owner=? AND source_system=? AND source_record_id=?",
                       (owner, source_system, source_record_id))

    def lookup(self, *, owner: str, lane: str, namespace: str, predicate: str,
               purpose: str, resolve: FactResolver, include_sensitive: bool = False,
               limit: int = 12) -> tuple[PersonalFactRef, ...]:
        if purpose not in {"retrieval", "analysis", "chat"}:
            return ()
        controlled = self._predicate(predicate)
        try:
            amount = min(MAX_LOOKUP, max(1, int(limit)))
            uri = self.path.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=0.01) as db:
                db.execute("PRAGMA query_only=ON")
                version = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
                if version is None or version[0] != str(SCHEMA_VERSION):
                    return ()
                rows = db.execute("""
                    SELECT source_system,source_record_id,revision,value_ref
                    FROM personal_facts
                    WHERE owner=? AND lane=? AND namespace=? AND predicate=?
                    ORDER BY source_record_id LIMIT ?
                """, (owner, lane, namespace, controlled, amount)).fetchall()
            found = []
            for system, record_id, revision, value_ref in rows:
                fact = resolve(owner, system, record_id)
                if fact is None or fact.source.revision != revision:
                    continue
                if fact.value_ref != value_ref or fact.predicate != controlled:
                    continue
                if (fact.source.owner, fact.source.lane, fact.source.namespace) != (owner, lane, namespace):
                    continue
                if not fact.visible_for(purpose, include_sensitive=include_sensitive):
                    continue
                found.append(fact)
            return tuple(found)
        except Exception:
            return ()
