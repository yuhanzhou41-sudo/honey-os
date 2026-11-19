"""Campus 校园快照存储（SQLite，独立于 Study 数据）。"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from honeyos.campus.snapshot import ExamRow, TimetableRow


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class CampusRepository:
    def __init__(self, home: Path | str | None = None):
        root = Path(home) if home is not None else Path.home() / ".honeyos"
        self.campus_dir = root / "campus"
        self.db_path = self.campus_dir / "campus.db"
        self.campus_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS campus_exam_records (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    batch_key TEXT NOT NULL,
                    course TEXT NOT NULL,
                    exam_date TEXT NOT NULL,
                    arrangement TEXT NOT NULL,
                    location TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_campus_exams_source
                    ON campus_exam_records(source, captured_at);
                CREATE TABLE IF NOT EXISTS campus_snapshot_meta (
                    source TEXT PRIMARY KEY,
                    batch_key TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campus_sync_runs (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    result TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    detail TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campus_timetable_records (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    batch_key TEXT NOT NULL,
                    day TEXT NOT NULL,
                    period TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_campus_timetable_source
                    ON campus_timetable_records(source, captured_at);
                CREATE TABLE IF NOT EXISTS campus_timetable_meta (
                    source TEXT PRIMARY KEY,
                    batch_key TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT NOT NULL
                );
                """
            )

    def latest_captured_at(self, source: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT captured_at FROM campus_snapshot_meta WHERE source = ?",
                (source,),
            ).fetchone()
        return row["captured_at"] if row else None

    def import_snapshot(
        self,
        source: str,
        batch_key: str,
        captured_at: str,
        rows: list[ExamRow],
    ) -> int:
        """整批事务替换该来源的考试记录；迟到旧响应由 service 层先行拦截。"""
        now = _utc_now()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM campus_exam_records WHERE source = ?", (source,))
            for row in rows:
                cursor.execute(
                    "INSERT INTO campus_exam_records (id, source, batch_key, course, exam_date,"
                    " arrangement, location, fingerprint, captured_at, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        _new_id("exam"),
                        source,
                        batch_key,
                        row.course,
                        row.exam_date,
                        row.arrangement,
                        row.location,
                        row.fingerprint,
                        captured_at,
                        now,
                    ),
                )
            cursor.execute(
                "INSERT INTO campus_snapshot_meta (source, batch_key, captured_at, row_count,"
                " last_attempt_at, last_success_at) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(source) DO UPDATE SET batch_key=excluded.batch_key,"
                " captured_at=excluded.captured_at, row_count=excluded.row_count,"
                " last_attempt_at=excluded.last_attempt_at, last_success_at=excluded.last_success_at",
                (source, batch_key, captured_at, len(rows), now, now),
            )
            cursor.execute(
                "INSERT INTO campus_sync_runs (id, source, result, row_count, detail, finished_at)"
                " VALUES (?,?,?,?,?,?)",
                (_new_id("run"), source, "imported", len(rows), batch_key, now),
            )
        return len(rows)

    def list_exams(self) -> dict:
        with self._connect() as conn:
            meta_rows = conn.execute(
                "SELECT source, batch_key, captured_at, row_count, last_attempt_at,"
                " last_success_at FROM campus_snapshot_meta"
            ).fetchall()
            record_rows = conn.execute(
                "SELECT id, source, batch_key, course, exam_date, arrangement, location,"
                " fingerprint, captured_at FROM campus_exam_records"
                " ORDER BY exam_date, course"
            ).fetchall()
        return {
            "records": [dict(row) for row in record_rows],
            "meta": [dict(row) for row in meta_rows],
        }

    def latest_timetable_captured_at(self, source: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT captured_at FROM campus_timetable_meta WHERE source = ?",
                (source,),
            ).fetchone()
        return row["captured_at"] if row else None

    def import_timetable(
        self,
        source: str,
        batch_key: str,
        captured_at: str,
        rows: list[TimetableRow],
    ) -> int:
        """整批事务替换该来源的课表记录；迟到旧响应由 service 层先行拦截。"""
        now = _utc_now()
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM campus_timetable_records WHERE source = ?", (source,))
            for row in rows:
                cursor.execute(
                    "INSERT INTO campus_timetable_records (id, source, batch_key, day, period,"
                    " detail, fingerprint, captured_at, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        _new_id("course"),
                        source,
                        batch_key,
                        row.day,
                        row.period,
                        row.detail,
                        row.fingerprint,
                        captured_at,
                        now,
                    ),
                )
            cursor.execute(
                "INSERT INTO campus_timetable_meta (source, batch_key, captured_at, row_count,"
                " last_attempt_at, last_success_at) VALUES (?,?,?,?,?,?)"
                " ON CONFLICT(source) DO UPDATE SET batch_key=excluded.batch_key,"
                " captured_at=excluded.captured_at, row_count=excluded.row_count,"
                " last_attempt_at=excluded.last_attempt_at, last_success_at=excluded.last_success_at",
                (source, batch_key, captured_at, len(rows), now, now),
            )
            cursor.execute(
                "INSERT INTO campus_sync_runs (id, source, result, row_count, detail, finished_at)"
                " VALUES (?,?,?,?,?,?)",
                (_new_id("run"), source, "imported_timetable", len(rows), batch_key, now),
            )
        return len(rows)

    def list_timetable(self) -> dict:
        with self._connect() as conn:
            meta_rows = conn.execute(
                "SELECT source, batch_key, captured_at, row_count, last_attempt_at,"
                " last_success_at FROM campus_timetable_meta"
            ).fetchall()
            record_rows = conn.execute(
                "SELECT id, source, batch_key, day, period, detail, fingerprint, captured_at"
                " FROM campus_timetable_records ORDER BY day, period, detail"
            ).fetchall()
        return {
            "records": [dict(row) for row in record_rows],
            "meta": [dict(row) for row in meta_rows],
        }
