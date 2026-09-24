from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from honeyos.core.constants import get_honeyos_home
from .models import (
    MemoryEpisode,
    MemoryFact,
    MemoryProvenance,
    ProceduralMemory,
    SuppressionTombstone,
)
from .schema import initialize_schema
from .suppression import (
    content_fingerprint,
    fact_fingerprint,
    normalize_subject_key,
    procedural_fingerprint,
)


class MemoryNotFoundError(KeyError):
    pass


class MemorySuppressedError(RuntimeError):
    def __init__(self, matches):
        self.matches = matches
        super().__init__("memory write blocked by suppression tombstone")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _load_json(value):
    if not value:
        return {}
    try:
        x = json.loads(value)
        return x if isinstance(x, dict) else {}
    except Exception:
        return {}


def _validate_source_identity(*, memory_origin: str, source_system: str, source_scope: str | None, source_key: str | None) -> None:
    if memory_origin not in {"native", "external"}:
        raise ValueError("memory_origin must be 'native' or 'external'")
    system = str(source_system or "").strip()
    if not system:
        raise ValueError("source_system is required")
    is_honeyos = system == "honeyos" or system.startswith("honeyos_")
    if memory_origin == "native":
        if not is_honeyos:
            raise ValueError("native memory must use a HoneyOS-owned source_system")
        return
    if is_honeyos:
        raise ValueError("external memory cannot use a HoneyOS-native source_system")
    if not str(source_scope or "").strip():
        raise ValueError("external memory requires source_scope")
    if not str(source_key or "").strip():
        raise ValueError("external memory requires source_key")


class CognitiveMemoryRepository:
    def __init__(self, honeyos_home=None, *, db_path=None):
        home = (
            Path(honeyos_home).expanduser()
            if honeyos_home is not None
            else Path(get_honeyos_home()).expanduser()
        )

        self.memory_dir = home / "memory"
        self.db_path = (
            Path(db_path).expanduser()
            if db_path is not None
            else self.memory_dir / "cognitive_memory.sqlite"
        )

        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with self.connect() as db:
            initialize_schema(db)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def create_tombstone(
        self,
        *,
        scope,
        reason,
        content=None,
        content_fp=None,
        subject_key=None,
        source_system=None,
        source_id=None,
        memory_kind=None,
        memory_id=None,
        metadata=None,
    ):
        fp = content_fp or (
            content_fingerprint(content) if content is not None else None
        )
        subject = (
            normalize_subject_key(subject_key)
            if subject_key is not None
            else None
        )

        if scope == "content" and not fp:
            raise ValueError("content tombstone requires content")
        if scope == "subject" and not subject:
            raise ValueError("subject tombstone requires subject_key")
        if scope == "source" and (not source_system or not source_id):
            raise ValueError("source tombstone requires source_system/source_id")
        if scope == "memory" and (not memory_kind or not memory_id):
            raise ValueError("memory tombstone requires memory_kind/memory_id")

        tid = "mt_" + uuid4().hex

        with self.connect() as db:
            db.execute(
                """
                INSERT INTO memory_tombstones(
                    tombstone_id,scope,memory_kind,memory_id,
                    subject_key,source_system,source_id,
                    content_fingerprint,reason,active,
                    created_at,lifted_at,metadata_json
                )
                VALUES (?,?,?,?,?,?,?,?,?,1,?,NULL,?)
                """,
                (
                    tid, scope, memory_kind, memory_id,
                    subject, source_system, source_id,
                    fp, reason, _now(), _json(metadata),
                ),
            )

        return self.get_tombstone(tid)

    def get_tombstone(self, tid):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM memory_tombstones WHERE tombstone_id=?",
                (tid,),
            ).fetchone()
        if not row:
            raise MemoryNotFoundError(tid)
        return self._tombstone(row)

    def lift_tombstone(self, tid):
        with self.connect() as db:
            db.execute(
                "UPDATE memory_tombstones SET active=0,lifted_at=? WHERE tombstone_id=?",
                (_now(), tid),
            )
        return self.get_tombstone(tid)

    def find_suppressions(
        self,
        *,
        content=None,
        content_fp=None,
        subject_key=None,
        source_system=None,
        source_id=None,
    ):
        clauses = []
        args = []

        fp = content_fp or (
            content_fingerprint(content) if content is not None else None
        )

        if fp:
            clauses.append("content_fingerprint=?")
            args.append(fp)

        if subject_key:
            clauses.append("(scope='subject' AND subject_key=?)")
            args.append(normalize_subject_key(subject_key))

        if source_system and source_id:
            clauses.append(
                "(scope='source' AND source_system=? AND source_id=?)"
            )
            args += [source_system, source_id]

        if not clauses:
            return []

        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM memory_tombstones "
                "WHERE active=1 AND (" + " OR ".join(clauses) + ")",
                args,
            ).fetchall()

        return [self._tombstone(r) for r in rows]

    def assert_not_suppressed(self, **kwargs):
        matches = self.find_suppressions(**kwargs)
        if matches:
            raise MemorySuppressedError(matches)

    def suppress_content(self, content, *, reason="user_explicit_forget"):
        return self.create_tombstone(
            scope="content",
            content=content,
            reason=reason,
        )

    def suppress_subject(self, subject_key, *, reason="user_explicit_forget"):
        return self.create_tombstone(
            scope="subject",
            subject_key=subject_key,
            reason=reason,
        )

    def suppress_source(self, source_system, source_id, *, reason="user_explicit_forget"):
        return self.create_tombstone(
            scope="source",
            source_system=source_system,
            source_id=source_id,
            reason=reason,
        )


    def suppress_memory(
        self,
        memory_kind,
        memory_id,
        *,
        reason="user_explicit_forget",
        metadata=None,
    ):
        """
        Explicitly forget an existing memory.

        The memory status transition and anti-recreation tombstone are
        committed in the same SQLite transaction. Therefore the repository
        can never expose a user_suppressed memory without its tombstone.
        """

        if memory_kind == "episode":
            table = "memory_episodes"
            id_column = "episode_id"

        elif memory_kind == "fact":
            table = "memory_facts"
            id_column = "fact_id"

        elif memory_kind == "procedural":
            table = "procedural_memories"
            id_column = "procedure_id"

        else:
            raise ValueError(
                f"unsupported memory kind: {memory_kind}"
            )

        tid = "mt_" + uuid4().hex
        now = _now()

        with self.connect() as db:
            row = db.execute(
                f"""
                SELECT content_fingerprint
                FROM {table}
                WHERE {id_column}=?
                """,
                (memory_id,),
            ).fetchone()

            if row is None:
                raise MemoryNotFoundError(memory_id)

            fp = row["content_fingerprint"]

            if table == "memory_episodes":
                db.execute(
                    """
                    UPDATE memory_episodes
                    SET status='user_suppressed'
                    WHERE episode_id=?
                    """,
                    (memory_id,),
                )
            else:
                db.execute(
                    f"""
                    UPDATE {table}
                    SET status='user_suppressed',
                        updated_at=?
                    WHERE {id_column}=?
                    """,
                    (now, memory_id),
                )

            db.execute(
                """
                INSERT INTO memory_tombstones(
                    tombstone_id,
                    scope,
                    memory_kind,
                    memory_id,
                    subject_key,
                    source_system,
                    source_id,
                    content_fingerprint,
                    reason,
                    active,
                    created_at,
                    lifted_at,
                    metadata_json
                )
                VALUES (
                    ?,
                    'memory',
                    ?,
                    ?,
                    NULL,
                    NULL,
                    NULL,
                    ?,
                    ?,
                    1,
                    ?,
                    NULL,
                    ?
                )
                """,
                (
                    tid,
                    memory_kind,
                    memory_id,
                    fp,
                    reason,
                    now,
                    _json(metadata),
                ),
            )

        return self.get_tombstone(tid)

    def create_episode(
        self,
        *,
        summary,
        episode_type="general",
        occurred_at=None,
        memory_origin="native",
        source_system="honeyos",
        source_scope=None,
        source_key=None,
        confidence=1.0,
        metadata=None,
        episode_id=None,
    ):
        summary = str(summary).strip()

        _validate_source_identity(
            memory_origin=memory_origin,
            source_system=source_system,
            source_scope=source_scope,
            source_key=source_key,
        )

        fp = content_fingerprint(summary)

        self.assert_not_suppressed(
            content_fp=fp,
            source_system=source_system,
            source_id=source_key,
        )

        eid = episode_id or "me_" + uuid4().hex
        now = _now()

        with self.connect() as db:
            db.execute(
                """
                INSERT INTO memory_episodes(
                    episode_id,episode_type,summary,occurred_at,captured_at,
                    status,memory_origin,
                    source_system,source_scope,source_key,
                    confidence,content_fingerprint,metadata_json
                )
                VALUES (?,?,?,?,?,'active',?,?,?,?,?,?,?)
                """,
                (
                    eid, episode_type, summary, occurred_at, now,
                    memory_origin,
                    source_system, source_scope, source_key,
                    confidence, fp, _json(metadata),
                ),
            )

        return self.get_episode(eid)

    def get_episode(self, eid):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM memory_episodes WHERE episode_id=?",
                (eid,),
            ).fetchone()
        if not row:
            raise MemoryNotFoundError(eid)
        return MemoryEpisode(
            episode_id=row["episode_id"],
            episode_type=row["episode_type"],
            summary=row["summary"],
            occurred_at=row["occurred_at"],
            captured_at=row["captured_at"],
            status=row["status"],
            memory_origin=row["memory_origin"],
            source_system=row["source_system"],
            source_scope=row["source_scope"],
            source_key=row["source_key"],
            confidence=row["confidence"],
            content_fingerprint=row["content_fingerprint"],
            metadata=_load_json(row["metadata_json"]),
        )

    def create_fact(
        self,
        *,
        subject,
        predicate,
        object_text,
        valid_from=None,
        valid_to=None,
        confidence=1.0,
        derived_from_episode_id=None,
        memory_origin="native",
        source_system="honeyos",
        source_scope=None,
        source_key=None,
        metadata=None,
        fact_id=None,
    ):
        _validate_source_identity(
            memory_origin=memory_origin,
            source_system=source_system,
            source_scope=source_scope,
            source_key=source_key,
        )

        fp = fact_fingerprint(subject, predicate, object_text)

        self.assert_not_suppressed(
            content_fp=fp,
            subject_key=subject,
        )

        fid = fact_id or "mf_" + uuid4().hex
        now = _now()

        with self.connect() as db:
            db.execute(
                """
                INSERT INTO memory_facts(
                    fact_id,subject,predicate,object_text,status,
                    valid_from,valid_to,confidence,
                    derived_from_episode_id,
                    memory_origin,source_system,source_scope,source_key,
                    content_fingerprint,
                    metadata_json,created_at,updated_at
                )
                VALUES (?,?,?,?,'current',?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fid, subject, predicate, object_text,
                    valid_from, valid_to, confidence,
                    derived_from_episode_id,
                    memory_origin, source_system, source_scope, source_key,
                    fp, _json(metadata), now, now,
                ),
            )

        return self.get_fact(fid)

    def get_fact(self, fid):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM memory_facts WHERE fact_id=?",
                (fid,),
            ).fetchone()
        if not row:
            raise MemoryNotFoundError(fid)
        return MemoryFact(
            fact_id=row["fact_id"],
            subject=row["subject"],
            predicate=row["predicate"],
            object_text=row["object_text"],
            status=row["status"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            confidence=row["confidence"],
            derived_from_episode_id=row["derived_from_episode_id"],
            memory_origin=row["memory_origin"],
            source_system=row["source_system"],
            source_scope=row["source_scope"],
            source_key=row["source_key"],
            content_fingerprint=row["content_fingerprint"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=_load_json(row["metadata_json"]),
        )

    def create_procedural(
        self,
        *,
        key,
        instruction,
        confidence=1.0,
        memory_origin="native",
        source_system="honeyos",
        source_scope=None,
        source_key=None,
        metadata=None,
        procedure_id=None,
    ):
        _validate_source_identity(
            memory_origin=memory_origin,
            source_system=source_system,
            source_scope=source_scope,
            source_key=source_key,
        )

        fp = procedural_fingerprint(key, instruction)

        self.assert_not_suppressed(
            content_fp=fp,
            subject_key=key,
        )

        pid = procedure_id or "mp_" + uuid4().hex
        now = _now()

        with self.connect() as db:
            db.execute(
                """
                INSERT INTO procedural_memories(
                    procedure_id,key,instruction,status,confidence,
                    valid_from,valid_to,
                    memory_origin,source_system,source_scope,source_key,
                    content_fingerprint,
                    metadata_json,created_at,updated_at
                )
                VALUES (?, ?, ?, 'active', ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pid, key, instruction, confidence,
                    memory_origin, source_system, source_scope, source_key,
                    fp, _json(metadata), now, now,
                ),
            )

        return self.get_procedural(pid)

    def get_procedural(self, pid):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM procedural_memories WHERE procedure_id=?",
                (pid,),
            ).fetchone()
        if not row:
            raise MemoryNotFoundError(pid)
        return ProceduralMemory(
            procedure_id=row["procedure_id"],
            key=row["key"],
            instruction=row["instruction"],
            status=row["status"],
            confidence=row["confidence"],
            memory_origin=row["memory_origin"],
            source_system=row["source_system"],
            source_scope=row["source_scope"],
            source_key=row["source_key"],
            valid_from=row["valid_from"],
            valid_to=row["valid_to"],
            content_fingerprint=row["content_fingerprint"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=_load_json(row["metadata_json"]),
        )

    def add_provenance(
        self,
        *,
        memory_kind,
        memory_id,
        source_system,
        source_type,
        source_id=None,
        session_id=None,
        message_id=None,
        evidence_quote=None,
        content_hash=None,
        metadata=None,
    ):
        pid = "mv_" + uuid4().hex
        now = _now()

        with self.connect() as db:
            db.execute(
                """
                INSERT INTO memory_provenance(
                    provenance_id,memory_kind,memory_id,
                    source_system,source_type,source_id,
                    session_id,message_id,evidence_quote,
                    content_hash,metadata_json,created_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    pid,memory_kind,memory_id,
                    source_system,source_type,source_id,
                    session_id,message_id,evidence_quote,
                    content_hash,_json(metadata),now,
                ),
            )

            row = db.execute(
                "SELECT * FROM memory_provenance WHERE provenance_id=?",
                (pid,),
            ).fetchone()

        return MemoryProvenance(
            provenance_id=row["provenance_id"],
            memory_kind=row["memory_kind"],
            memory_id=row["memory_id"],
            source_system=row["source_system"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            session_id=row["session_id"],
            message_id=row["message_id"],
            evidence_quote=row["evidence_quote"],
            content_hash=row["content_hash"],
            created_at=row["created_at"],
            metadata=_load_json(row["metadata_json"]),
        )

    @staticmethod
    def _tombstone(row):
        return SuppressionTombstone(
            tombstone_id=row["tombstone_id"],
            scope=row["scope"],
            memory_kind=row["memory_kind"],
            memory_id=row["memory_id"],
            subject_key=row["subject_key"],
            source_system=row["source_system"],
            source_id=row["source_id"],
            content_fingerprint=row["content_fingerprint"],
            reason=row["reason"],
            active=bool(row["active"]),
            created_at=row["created_at"],
            lifted_at=row["lifted_at"],
            metadata=_load_json(row["metadata_json"]),
        )
