"""Campus 校园快照存储（SQLite，独立于 Study 数据）。

同一来源可能对应多个校园账号（例如两个专业各一个账号），记录与
元数据都按 ``account`` 隔离；不同账号的整批替换互不影响。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from honeyos.campus.snapshot import (
    DEFAULT_ACCOUNT,
    ExamRow,
    GradeRow,
    TimetableRow,
)


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
                    account TEXT NOT NULL DEFAULT 'default',
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
                CREATE TABLE IF NOT EXISTS campus_timetable_records (
                    id TEXT PRIMARY KEY,
                    account TEXT NOT NULL DEFAULT 'default',
                    source TEXT NOT NULL,
                    batch_key TEXT NOT NULL,
                    day TEXT NOT NULL,
                    period TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campus_grade_records (
                    id TEXT PRIMARY KEY,
                    account TEXT NOT NULL DEFAULT 'default',
                    source TEXT NOT NULL,
                    batch_key TEXT NOT NULL,
                    course TEXT NOT NULL,
                    score TEXT NOT NULL,
                    credit TEXT NOT NULL,
                    term TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campus_meta (
                    account TEXT NOT NULL,
                    source TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    batch_key TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    last_attempt_at TEXT NOT NULL,
                    last_success_at TEXT NOT NULL,
                    PRIMARY KEY (account, source, kind)
                );
                CREATE TABLE IF NOT EXISTS campus_sync_runs (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    result TEXT NOT NULL,
                    row_count INTEGER NOT NULL DEFAULT 0,
                    detail TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL
                );
                """
            )
            # 旧库的表已存在时 CREATE TABLE IF NOT EXISTS 不会补列，
            # 必须先补 account 列，再建依赖该列的索引。
            self._ensure_account_column(conn, "campus_exam_records")
            self._ensure_account_column(conn, "campus_timetable_records")
            self._ensure_account_column(conn, "campus_grade_records")
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_campus_exams_account
                    ON campus_exam_records(account, source, captured_at);
                CREATE INDEX IF NOT EXISTS idx_campus_timetable_account
                    ON campus_timetable_records(account, source, captured_at);
                CREATE INDEX IF NOT EXISTS idx_campus_grades_account
                    ON campus_grade_records(account, source, captured_at);
                """
            )
            self._migrate_legacy_meta(conn)

    @staticmethod
    def _ensure_account_column(conn: sqlite3.Connection, table: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if "account" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN account TEXT NOT NULL DEFAULT 'default'"
            )

    @staticmethod
    def _migrate_legacy_meta(conn: sqlite3.Connection) -> None:
        """把加入账号隔离前的单账号元数据搬进 campus_meta，避免丢历史。"""
        legacy = (
            ("campus_snapshot_meta", "exams"),
            ("campus_timetable_meta", "timetable"),
        )
        for table, kind in legacy:
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                continue
            for row in rows:
                conn.execute(
                    "INSERT OR IGNORE INTO campus_meta (account, source, kind, batch_key,"
                    " captured_at, row_count, last_attempt_at, last_success_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (
                        DEFAULT_ACCOUNT,
                        row["source"],
                        kind,
                        row["batch_key"],
                        row["captured_at"],
                        row["row_count"],
                        row["last_attempt_at"],
                        row["last_success_at"],
                    ),
                )

    @staticmethod
    def _resolve_account(conn: sqlite3.Connection, kind: str, account: str | None) -> str:
        if account:
            return account
        row = conn.execute(
            "SELECT account FROM campus_meta WHERE kind = ?"
            " ORDER BY captured_at DESC LIMIT 1",
            (kind,),
        ).fetchone()
        return row["account"] if row else DEFAULT_ACCOUNT

    def latest_captured_at(self, source: str, account: str = DEFAULT_ACCOUNT,
                           kind: str = "exams") -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT captured_at FROM campus_meta"
                " WHERE account = ? AND source = ? AND kind = ?",
                (account, source, kind),
            ).fetchone()
        return row["captured_at"] if row else None

    def _import_rows(
        self,
        table: str,
        kind: str,
        row_columns: list[str],
        account: str,
        source: str,
        batch_key: str,
        captured_at: str,
        rows: list,
    ) -> int:
        now = _utc_now()
        placeholders = ",".join("?" for _ in range(3 + len(row_columns) + 4))
        columns = "id, account, source, batch_key, " + ", ".join(row_columns) \
            + ", fingerprint, captured_at, created_at"
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM {table} WHERE account = ? AND source = ?",
                (account, source),
            )
            for row in rows:
                values = [_new_id("rec"), account, source, batch_key]
                values.extend(getattr(row, name) for name in row_columns)
                values.extend([row.fingerprint, captured_at, now])
                cursor.execute(
                    f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                    values,
                )
            cursor.execute(
                "INSERT INTO campus_meta (account, source, kind, batch_key, captured_at,"
                " row_count, last_attempt_at, last_success_at) VALUES (?,?,?,?,?,?,?,?)"
                " ON CONFLICT(account, source, kind) DO UPDATE SET"
                " batch_key=excluded.batch_key, captured_at=excluded.captured_at,"
                " row_count=excluded.row_count, last_attempt_at=excluded.last_attempt_at,"
                " last_success_at=excluded.last_success_at",
                (account, source, kind, batch_key, captured_at, len(rows), now, now),
            )
            cursor.execute(
                "INSERT INTO campus_sync_runs (id, source, result, row_count, detail, finished_at)"
                " VALUES (?,?,?,?,?,?)",
                (_new_id("run"), source, f"imported_{kind}", len(rows), batch_key, now),
            )
        return len(rows)

    def import_snapshot(
        self,
        source: str,
        batch_key: str,
        captured_at: str,
        rows: list[ExamRow],
        account: str = DEFAULT_ACCOUNT,
    ) -> int:
        """整批事务替换该账号的考试记录；迟到旧响应由 service 层先行拦截。"""
        return self._import_rows(
            "campus_exam_records",
            "exams",
            ["course", "exam_date", "arrangement", "location"],
            account,
            source,
            batch_key,
            captured_at,
            rows,
        )

    def import_timetable(
        self,
        source: str,
        batch_key: str,
        captured_at: str,
        rows: list[TimetableRow],
        account: str = DEFAULT_ACCOUNT,
    ) -> int:
        """整批事务替换该账号的课表记录。"""
        return self._import_rows(
            "campus_timetable_records",
            "timetable",
            ["day", "period", "detail"],
            account,
            source,
            batch_key,
            captured_at,
            rows,
        )

    def import_grades(
        self,
        source: str,
        batch_key: str,
        captured_at: str,
        rows: list[GradeRow],
        account: str = DEFAULT_ACCOUNT,
    ) -> int:
        """整批事务替换该账号的成绩记录。"""
        return self._import_rows(
            "campus_grade_records",
            "grades",
            ["course", "score", "credit", "term"],
            account,
            source,
            batch_key,
            captured_at,
            rows,
        )

    def _list(
        self,
        table: str,
        kind: str,
        select_fields: list[str],
        order_by: str,
        account: str | None,
    ) -> dict:
        with self._connect() as conn:
            resolved = self._resolve_account(conn, kind, account)
            meta_rows = conn.execute(
                "SELECT account, source, batch_key, captured_at, row_count,"
                " last_attempt_at, last_success_at FROM campus_meta"
                " WHERE kind = ? AND account = ?",
                (kind, resolved),
            ).fetchall()
            record_rows = conn.execute(
                "SELECT id, account, source, batch_key, " + ", ".join(select_fields)
                + ", fingerprint, captured_at FROM " + table
                + " WHERE account = ? ORDER BY " + order_by,
                (resolved,),
            ).fetchall()
        return {
            "account": resolved,
            "records": [dict(row) for row in record_rows],
            "meta": [dict(row) for row in meta_rows],
        }

    def list_exams(self, account: str | None = None) -> dict:
        return self._list(
            "campus_exam_records",
            "exams",
            ["course", "exam_date", "arrangement", "location"],
            "exam_date, course",
            account,
        )

    def list_timetable(self, account: str | None = None) -> dict:
        return self._list(
            "campus_timetable_records",
            "timetable",
            ["day", "period", "detail"],
            "day, period, detail",
            account,
        )

    def list_grades(self, account: str | None = None) -> dict:
        return self._list(
            "campus_grade_records",
            "grades",
            ["course", "score", "credit", "term"],
            "term, course",
            account,
        )

    def list_accounts(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT account, kind, MAX(captured_at) AS captured_at, SUM(row_count) AS row_count"
                " FROM campus_meta GROUP BY account, kind ORDER BY account"
            ).fetchall()
        return [dict(row) for row in rows]
