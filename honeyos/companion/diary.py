"""Profile-local storage for the companion shared diary.

Diary entries are intentionally isolated from HoneyOS memory files.  Reading
this store never makes an entry part of model context; that requires an
explicit, separately audited claim operation in the chat lifecycle.
"""

from __future__ import annotations

import sqlite3
import uuid
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

DiaryAuthor = Literal["user", "assistant"]
MAX_DIARY_CONTENT_LENGTH = 20_000
DIARY_MEMORY_WEIGHT = 3


@dataclass(frozen=True)
class DiaryEntry:
    id: str
    author: DiaryAuthor
    entry_date: str
    content: str
    created_at: str
    updated_at: str
    allow_ai_view: bool = True
    allow_memory: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DiaryMemoryBucket:
    entry_date: str
    content: str
    version: str
    weight: int = DIARY_MEMORY_WEIGHT

    @property
    def evidence_id(self) -> int:
        """Use a stable negative integer namespace beside chat row IDs."""

        return -int(self.entry_date.replace("-", ""))


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
                updated_at TEXT NOT NULL,
                allow_ai_view INTEGER NOT NULL DEFAULT 1,
                allow_memory INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(diary_entries)")
        }
        if "allow_ai_view" not in columns:
            connection.execute(
                "ALTER TABLE diary_entries ADD COLUMN allow_ai_view INTEGER NOT NULL DEFAULT 1"
            )
        if "allow_memory" not in columns:
            connection.execute(
                "ALTER TABLE diary_entries ADD COLUMN allow_memory INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS diary_entries_date_idx "
            "ON diary_entries(entry_date DESC, created_at DESC)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS diary_one_assistant_per_day_idx "
            "ON diary_entries(entry_date) WHERE author = 'assistant'"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS diary_daily_state (
                entry_date TEXT PRIMARY KEY,
                user_read_claimed_at TEXT,
                user_read_cutoff TEXT,
                generation_status TEXT NOT NULL DEFAULT 'idle'
                    CHECK(generation_status IN ('idle', 'pending', 'completed', 'failed')),
                generation_started_at TEXT,
                generation_completed_at TEXT,
                assistant_entry_id TEXT,
                generation_error TEXT NOT NULL DEFAULT '',
                user_read_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        state_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(diary_daily_state)")
        }
        if "generation_completed_at" not in state_columns:
            connection.execute(
                "ALTER TABLE diary_daily_state ADD COLUMN generation_completed_at TEXT"
            )
        if "user_read_count" not in state_columns:
            connection.execute(
                "ALTER TABLE diary_daily_state ADD COLUMN user_read_count INTEGER NOT NULL DEFAULT 0"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS diary_memory_state (
                entry_date TEXT PRIMARY KEY,
                processed_version TEXT NOT NULL,
                processed_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS diary_user_updates_idx "
            "ON diary_entries(updated_at) WHERE author = 'user'"
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
        values = dict(row)
        values["allow_ai_view"] = bool(values.get("allow_ai_view", 1))
        values["allow_memory"] = bool(values.get("allow_memory", 0))
        return DiaryEntry(**values)

    @staticmethod
    def _permissions(*, allow_ai_view: bool, allow_memory: bool) -> tuple[bool, bool]:
        """Normalize the invariant that remembering necessarily permits reading."""

        remember = bool(allow_memory)
        return bool(allow_ai_view) or remember, remember

    def list_entries(self, *, limit: int = 100) -> tuple[DiaryEntry, ...]:
        bounded = max(1, min(int(limit), 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, author, entry_date, content, created_at, updated_at, "
                "allow_ai_view, allow_memory "
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
        allow_ai_view: bool = True,
        allow_memory: bool = False,
    ) -> DiaryEntry:
        safe_author = self._validate_author(author)
        safe_date = self._validate_date(entry_date)
        safe_content = self._validate_content(content)
        now = datetime.now(timezone.utc).isoformat()
        can_view, can_remember = self._permissions(
            allow_ai_view=allow_ai_view, allow_memory=allow_memory
        )
        entry = DiaryEntry(
            id=f"diary_{uuid.uuid4().hex}",
            author=safe_author,
            entry_date=safe_date,
            content=safe_content,
            created_at=now,
            updated_at=now,
            allow_ai_view=can_view,
            allow_memory=can_remember,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO diary_entries "
                    "(id, author, entry_date, content, created_at, updated_at, "
                    "allow_ai_view, allow_memory) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry.id,
                        entry.author,
                        entry.entry_date,
                        entry.content,
                        entry.created_at,
                        entry.updated_at,
                        int(entry.allow_ai_view),
                        int(entry.allow_memory),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            if safe_author == "assistant":
                raise ValueError("assistant_diary_already_exists") from exc
            raise
        return entry

    def update_user_entry(
        self,
        entry_id: str,
        *,
        content: str | None = None,
        allow_ai_view: bool | None = None,
        allow_memory: bool | None = None,
    ) -> DiaryEntry | None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id, content, allow_ai_view, allow_memory FROM diary_entries "
                "WHERE id = ? AND author = 'user'",
                (entry_id,),
            ).fetchone()
            if existing is None:
                return None
            safe_content = (
                self._validate_content(content)
                if content is not None
                else str(existing["content"])
            )
            can_view, can_remember = self._permissions(
                allow_ai_view=(
                    bool(existing["allow_ai_view"])
                    if allow_ai_view is None
                    else allow_ai_view
                ),
                allow_memory=(
                    bool(existing["allow_memory"])
                    if allow_memory is None
                    else allow_memory
                ),
            )
            if allow_ai_view is False:
                can_view = False
                can_remember = False
            cursor = connection.execute(
                "UPDATE diary_entries SET content = ?, allow_ai_view = ?, "
                "allow_memory = ?, updated_at = ? "
                "WHERE id = ? AND author = 'user'",
                (safe_content, int(can_view), int(can_remember), now, entry_id),
            )
            if cursor.rowcount != 1:
                return None
            row = connection.execute(
                "SELECT id, author, entry_date, content, created_at, updated_at, "
                "allow_ai_view, allow_memory "
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

    def pending_memory_buckets(self) -> tuple[DiaryMemoryBucket, ...]:
        """Return one pending, permission-filtered evidence bucket per local date."""

        buckets: list[DiaryMemoryBucket] = []
        with self._connect() as connection:
            dates = connection.execute(
                "SELECT DISTINCT entry_date FROM diary_entries "
                "WHERE author = 'user' AND allow_memory = 1 ORDER BY entry_date"
            ).fetchall()
            for date_row in dates:
                entry_date = str(date_row["entry_date"])
                rows = connection.execute(
                    "SELECT id, content, updated_at FROM diary_entries "
                    "WHERE author = 'user' AND allow_memory = 1 AND entry_date = ? "
                    "ORDER BY created_at, id",
                    (entry_date,),
                ).fetchall()
                payload = [
                    (str(row["id"]), str(row["updated_at"]), str(row["content"]))
                    for row in rows
                ]
                if not payload:
                    continue
                version = hashlib.sha256(
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                        "utf-8"
                    )
                ).hexdigest()
                state = connection.execute(
                    "SELECT processed_version FROM diary_memory_state WHERE entry_date = ?",
                    (entry_date,),
                ).fetchone()
                if state is not None and str(state["processed_version"]) == version:
                    continue
                content = "\n\n".join(item[2] for item in payload)
                buckets.append(
                    DiaryMemoryBucket(
                        entry_date=entry_date,
                        content=content[:MAX_DIARY_CONTENT_LENGTH],
                        version=version,
                    )
                )
        return tuple(buckets)

    def mark_memory_buckets_processed(
        self, buckets: tuple[DiaryMemoryBucket, ...]
    ) -> None:
        """Checkpoint exactly the versions accepted by a successful review."""

        if not buckets:
            return
        processed_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.executemany(
                "INSERT INTO diary_memory_state "
                "(entry_date, processed_version, processed_at) VALUES (?, ?, ?) "
                "ON CONFLICT(entry_date) DO UPDATE SET "
                "processed_version = excluded.processed_version, "
                "processed_at = excluded.processed_at",
                [
                    (bucket.entry_date, bucket.version, processed_at)
                    for bucket in buckets
                ],
            )

    def claim_user_entries_for_day(
        self,
        entry_date: str,
        *,
        now: datetime | None = None,
    ) -> tuple[DiaryEntry, ...]:
        """Atomically return user changes once for one local calendar day."""

        safe_date = self._validate_date(entry_date)
        claimed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = connection.execute(
                "SELECT user_read_claimed_at FROM diary_daily_state WHERE entry_date = ?",
                (safe_date,),
            ).fetchone()
            if state is not None and state["user_read_claimed_at"]:
                connection.rollback()
                return ()
            previous = connection.execute(
                "SELECT user_read_cutoff FROM diary_daily_state "
                "WHERE user_read_cutoff IS NOT NULL AND entry_date < ? "
                "ORDER BY entry_date DESC LIMIT 1",
                (safe_date,),
            ).fetchone()
            previous_cutoff = str(previous["user_read_cutoff"] or "") if previous else ""
            if previous_cutoff:
                rows = connection.execute(
                    "SELECT id, author, entry_date, content, created_at, updated_at, "
                    "allow_ai_view, allow_memory "
                    "FROM diary_entries WHERE author = 'user' "
                    "AND allow_ai_view = 1 "
                    "AND updated_at > ? AND updated_at <= ? "
                    "ORDER BY updated_at, created_at",
                    (previous_cutoff, claimed_at),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT id, author, entry_date, content, created_at, updated_at, "
                    "allow_ai_view, allow_memory FROM diary_entries "
                    "WHERE author = 'user' AND allow_ai_view = 1 AND updated_at <= ? "
                    "ORDER BY updated_at, created_at",
                    (claimed_at,),
                ).fetchall()
            connection.execute(
                "INSERT INTO diary_daily_state "
                "(entry_date, user_read_claimed_at, user_read_cutoff, user_read_count) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(entry_date) DO UPDATE SET "
                "user_read_claimed_at = excluded.user_read_claimed_at, "
                "user_read_cutoff = excluded.user_read_cutoff, "
                "user_read_count = excluded.user_read_count",
                (safe_date, claimed_at, claimed_at, len(rows)),
            )
            connection.commit()
            return tuple(self._entry(row) for row in rows)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def begin_assistant_generation(
        self,
        entry_date: str,
        *,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(hours=1),
    ) -> bool:
        """Acquire the once-daily generation lease, recovering stale attempts."""

        safe_date = self._validate_date(entry_date)
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing_entry = connection.execute(
                "SELECT id FROM diary_entries WHERE author = 'assistant' AND entry_date = ?",
                (safe_date,),
            ).fetchone()
            if existing_entry is not None:
                connection.rollback()
                return False
            state = connection.execute(
                "SELECT generation_status, generation_started_at "
                "FROM diary_daily_state WHERE entry_date = ?",
                (safe_date,),
            ).fetchone()
            if state is not None and state["generation_status"] == "pending":
                try:
                    started = datetime.fromisoformat(state["generation_started_at"])
                    if current - started.astimezone(timezone.utc) < stale_after:
                        connection.rollback()
                        return False
                except (TypeError, ValueError):
                    pass
            connection.execute(
                "INSERT INTO diary_daily_state "
                "(entry_date, generation_status, generation_started_at, generation_error) "
                "VALUES (?, 'pending', ?, '') "
                "ON CONFLICT(entry_date) DO UPDATE SET generation_status = 'pending', "
                "generation_started_at = excluded.generation_started_at, "
                "generation_completed_at = NULL, generation_error = ''",
                (safe_date, current.isoformat()),
            )
            connection.commit()
            return True
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def finish_assistant_generation(self, entry_date: str, entry_id: str) -> None:
        safe_date = self._validate_date(entry_date)
        completed_at = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                "UPDATE diary_daily_state SET generation_status = 'completed', "
                "generation_completed_at = ?, assistant_entry_id = ?, "
                "generation_error = '' WHERE entry_date = ?",
                (completed_at, entry_id, safe_date),
            )

    def fail_assistant_generation(self, entry_date: str, error: str = "") -> None:
        safe_date = self._validate_date(entry_date)
        with self._connect() as connection:
            connection.execute(
                "UPDATE diary_daily_state SET generation_status = 'failed', "
                "generation_error = ? WHERE entry_date = ?",
                (str(error)[:500], safe_date),
            )

    def generation_status(self, entry_date: str) -> dict[str, object]:
        safe_date = self._validate_date(entry_date)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT entry_date, generation_status, generation_started_at, "
                "generation_completed_at, assistant_entry_id, generation_error, "
                "user_read_claimed_at, user_read_count FROM diary_daily_state "
                "WHERE entry_date = ?",
                (safe_date,),
            ).fetchone()
        if row is None:
            return {
                "entry_date": safe_date,
                "status": "idle",
                "started_at": None,
                "completed_at": None,
                "assistant_entry_id": None,
                "error": "",
                "user_read_at": None,
                "user_read_count": 0,
            }
        return {
            "entry_date": safe_date,
            "status": str(row["generation_status"]),
            "started_at": row["generation_started_at"],
            "completed_at": row["generation_completed_at"],
            "assistant_entry_id": row["assistant_entry_id"],
            "error": str(row["generation_error"] or ""),
            "user_read_at": row["user_read_claimed_at"],
            "user_read_count": int(row["user_read_count"] or 0),
        }
