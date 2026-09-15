"""Profile-local storage for the companion shared diary.

Diary entries are intentionally isolated from HoneyOS memory files.  Reading
this store never makes an entry part of model context; that requires an
explicit, separately audited claim operation in the chat lifecycle.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

DiaryAuthor = Literal["user", "assistant"]
MAX_DIARY_CONTENT_LENGTH = 20_000


@dataclass(frozen=True)
class DiaryEntry:
    id: str
    author: DiaryAuthor
    entry_date: str
    content: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class DiaryStore:
    """SQLite-backed diary scoped to one resolved HoneyOS home."""

    def __init__(self, home: Path):
        self.path = Path(home).expanduser().resolve() / "companion" / "diary.db"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS diary_entries (
                id TEXT PRIMARY KEY,
                author TEXT NOT NULL CHECK(author IN ('user', 'assistant')),
                entry_date TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS diary_entries_date_idx "
            "ON diary_entries(entry_date DESC, created_at DESC)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS diary_one_assistant_per_day_idx "
            "ON diary_entries(entry_date) WHERE author = 'assistant'"
        )
        return connection

    @staticmethod
    def _validate_author(author: str) -> DiaryAuthor:
        if author not in {"user", "assistant"}:
            raise ValueError("invalid_diary_author")
        return author  # type: ignore[return-value]

    @staticmethod
    def _validate_date(value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_diary_date") from exc
        if parsed.isoformat() != value:
            raise ValueError("invalid_diary_date")
        return value

    @staticmethod
    def _validate_content(content: str) -> str:
        value = str(content).strip()
        if not value:
            raise ValueError("diary_content_required")
        if len(value) > MAX_DIARY_CONTENT_LENGTH:
            raise ValueError("diary_content_too_long")
        return value

    @staticmethod
    def _entry(row: sqlite3.Row) -> DiaryEntry:
        return DiaryEntry(**dict(row))

    def list_entries(self, *, limit: int = 100) -> tuple[DiaryEntry, ...]:
        bounded = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, author, entry_date, content, created_at, updated_at "
                "FROM diary_entries ORDER BY entry_date DESC, created_at DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return tuple(self._entry(row) for row in rows)

    def create_entry(
        self,
        *,
        author: str,
        entry_date: str,
        content: str,
    ) -> DiaryEntry:
        safe_author = self._validate_author(author)
        safe_date = self._validate_date(entry_date)
        safe_content = self._validate_content(content)
        now = datetime.now(timezone.utc).isoformat()
        entry = DiaryEntry(
            id=f"diary_{uuid.uuid4().hex}",
            author=safe_author,
            entry_date=safe_date,
            content=safe_content,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO diary_entries "
                    "(id, author, entry_date, content, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        entry.id,
                        entry.author,
                        entry.entry_date,
                        entry.content,
                        entry.created_at,
                        entry.updated_at,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if safe_author == "assistant":
                raise ValueError("assistant_diary_already_exists") from exc
            raise
        return entry

    def update_user_entry(self, entry_id: str, *, content: str) -> DiaryEntry | None:
        safe_content = self._validate_content(content)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE diary_entries SET content = ?, updated_at = ? "
                "WHERE id = ? AND author = 'user'",
                (safe_content, now, entry_id),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT id, author, entry_date, content, created_at, updated_at "
                "FROM diary_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        return self._entry(row)

    def delete_user_entry(self, entry_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM diary_entries WHERE id = ? AND author = 'user'",
                (entry_id,),
            )
        return cursor.rowcount == 1
