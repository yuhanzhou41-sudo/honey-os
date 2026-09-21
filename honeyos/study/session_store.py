from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import StudySession


class StudySessionNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class StudySessionRuntime:
    session_id: str
    elapsed_seconds: int
    remaining_seconds: int
    last_resumed_at: datetime | None
    scheduler_job_id: str | None
    updated_at: datetime


class StudySessionStore:
    """Phase 3 persistence for StudySession runtime state."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self._init_runtime_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_runtime_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_study_sessions_task
                    ON study_sessions(task_id);

                CREATE TABLE IF NOT EXISTS study_session_runtime (
                    session_id TEXT PRIMARY KEY
                        REFERENCES study_sessions(id) ON DELETE CASCADE,
                    elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                    remaining_seconds INTEGER NOT NULL DEFAULT 0,
                    last_resumed_at TEXT,
                    scheduler_job_id TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def save_session(self, session: StudySession) -> StudySession:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO study_sessions (
                    id, task_id, session_type, status,
                    started_at, expected_end_at, ended_at,
                    planned_minutes, actual_minutes, user_summary,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    task_id=excluded.task_id,
                    session_type=excluded.session_type,
                    status=excluded.status,
                    started_at=excluded.started_at,
                    expected_end_at=excluded.expected_end_at,
                    ended_at=excluded.ended_at,
                    planned_minutes=excluded.planned_minutes,
                    actual_minutes=excluded.actual_minutes,
                    user_summary=excluded.user_summary,
                    updated_at=excluded.updated_at
                """,
                (
                    session.id,
                    session.task_id,
                    session.session_type.value,
                    session.status.value,
                    session.started_at.isoformat() if session.started_at else None,
                    session.expected_end_at.isoformat() if session.expected_end_at else None,
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.planned_minutes,
                    session.actual_minutes,
                    session.user_summary,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )
        return self.get_session(session.id)

    def get_session(self, session_id: str) -> StudySession:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM study_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise StudySessionNotFoundError(session_id)
        return StudySession.model_validate(dict(row))

    def list_sessions(self, task_id: str | None = None) -> list[StudySession]:
        with self._connect() as conn:
            if task_id:
                rows = conn.execute(
                    """
                    SELECT id FROM study_sessions
                    WHERE task_id = ?
                    ORDER BY created_at, id
                    """,
                    (task_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM study_sessions ORDER BY created_at, id"
                ).fetchall()
        return [self.get_session(row["id"]) for row in rows]

    def save_runtime(
        self,
        session_id: str,
        *,
        elapsed_seconds: int,
        remaining_seconds: int,
        last_resumed_at: datetime | None,
        scheduler_job_id: str | None,
        updated_at: datetime | None = None,
    ) -> StudySessionRuntime:
        stamp = updated_at or datetime.now(timezone.utc)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO study_session_runtime (
                    session_id, elapsed_seconds, remaining_seconds,
                    last_resumed_at, scheduler_job_id, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    elapsed_seconds=excluded.elapsed_seconds,
                    remaining_seconds=excluded.remaining_seconds,
                    last_resumed_at=excluded.last_resumed_at,
                    scheduler_job_id=excluded.scheduler_job_id,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    max(0, int(elapsed_seconds)),
                    max(0, int(remaining_seconds)),
                    last_resumed_at.isoformat() if last_resumed_at else None,
                    scheduler_job_id,
                    stamp.isoformat(),
                ),
            )
        return self.get_runtime(session_id)

    def get_runtime(self, session_id: str) -> StudySessionRuntime:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM study_session_runtime WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            session = self.get_session(session_id)
            return self.save_runtime(
                session.id,
                elapsed_seconds=max(0, session.actual_minutes * 60),
                remaining_seconds=max(
                    0, session.planned_minutes * 60 - session.actual_minutes * 60
                ),
                last_resumed_at=None,
                scheduler_job_id=None,
            )
        return StudySessionRuntime(
            session_id=row["session_id"],
            elapsed_seconds=int(row["elapsed_seconds"]),
            remaining_seconds=int(row["remaining_seconds"]),
            last_resumed_at=(
                datetime.fromisoformat(row["last_resumed_at"])
                if row["last_resumed_at"]
                else None
            ),
            scheduler_job_id=row["scheduler_job_id"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
