from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from honeyos.files.models import (
    Attachment,
    AttachmentSourceType,
    AttachmentStatus,
)
from honeyos.files.validation import validate_attachment


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AttachmentRepositoryError(RuntimeError):
    pass


class AttachmentNotFoundError(KeyError):
    pass


class AttachmentRepository:
    """SQLite metadata repository for HoneyOS attachments."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.db_path = self.root / "attachments.db"

    def _connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    declared_mime_type TEXT NOT NULL DEFAULT '',
                    inferred_mime_type TEXT NOT NULL DEFAULT '',
                    size_bytes INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_attachments_object_key
                    ON attachments(object_key);

                CREATE INDEX IF NOT EXISTS idx_attachments_sha256
                    ON attachments(sha256);

                CREATE INDEX IF NOT EXISTS idx_attachments_status
                    ON attachments(status);
                """
            )

    def save(self, attachment: Attachment) -> Attachment:
        attachment = validate_attachment(attachment)
        self.initialize()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO attachments (
                    id,
                    original_filename,
                    object_key,
                    declared_mime_type,
                    inferred_mime_type,
                    size_bytes,
                    sha256,
                    source_type,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    original_filename = excluded.original_filename,
                    object_key = excluded.object_key,
                    declared_mime_type = excluded.declared_mime_type,
                    inferred_mime_type = excluded.inferred_mime_type,
                    size_bytes = excluded.size_bytes,
                    sha256 = excluded.sha256,
                    source_type = excluded.source_type,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    attachment.id,
                    attachment.original_filename,
                    attachment.object_key,
                    attachment.declared_mime_type,
                    attachment.inferred_mime_type,
                    attachment.size_bytes,
                    attachment.sha256,
                    attachment.source_type.value,
                    attachment.status.value,
                    attachment.created_at.isoformat(),
                    attachment.updated_at.isoformat(),
                ),
            )

        return self.get(attachment.id)

    def get(self, attachment_id: str) -> Attachment:
        self.initialize()

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM attachments
                WHERE id = ?
                """,
                (attachment_id,),
            ).fetchone()

        if row is None:
            raise AttachmentNotFoundError(attachment_id)

        return self._row_to_attachment(row)

    def list(
        self,
        *,
        include_deleted: bool = False,
    ) -> list[Attachment]:
        self.initialize()

        query = """
            SELECT *
            FROM attachments
        """
        params: tuple[object, ...] = ()

        if not include_deleted:
            query += " WHERE status != ?"
            params = (AttachmentStatus.DELETED.value,)

        query += " ORDER BY created_at ASC, id ASC"

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        return [self._row_to_attachment(row) for row in rows]

    def soft_delete(self, attachment_id: str) -> Attachment:
        attachment = self.get(attachment_id)

        if attachment.status == AttachmentStatus.DELETED:
            return attachment

        now = datetime.now(timezone.utc)

        deleted = attachment.model_copy(
            update={
                "status": AttachmentStatus.DELETED,
                "updated_at": now,
            }
        )

        return self.save(deleted)

    def restore(self, attachment_id: str) -> Attachment:
        attachment = self.get(attachment_id)

        if attachment.status != AttachmentStatus.DELETED:
            return attachment

        now = datetime.now(timezone.utc)

        restored = attachment.model_copy(
            update={
                "status": AttachmentStatus.READY,
                "updated_at": now,
            }
        )

        return self.save(restored)

    def hard_delete(self, attachment_id: str) -> Attachment:
        attachment = self.get(attachment_id)

        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM attachments
                WHERE id = ?
                """,
                (attachment_id,),
            )

        return attachment

    def count_object_references(
        self,
        object_key: str,
        *,
        include_deleted: bool = False,
    ) -> int:
        self.initialize()

        query = """
            SELECT COUNT(*) AS count
            FROM attachments
            WHERE object_key = ?
        """
        params: list[object] = [object_key]

        if not include_deleted:
            query += " AND status != ?"
            params.append(AttachmentStatus.DELETED.value)

        with self._connect() as conn:
            row = conn.execute(query, tuple(params)).fetchone()

        return int(row["count"])

    def has_live_object_reference(self, object_key: str) -> bool:
        return self.count_object_references(
            object_key,
            include_deleted=False,
        ) > 0

    def find_by_sha256(
        self,
        sha256: str,
        *,
        include_deleted: bool = False,
    ) -> list[Attachment]:
        self.initialize()

        normalized = sha256.strip().lower()

        query = """
            SELECT *
            FROM attachments
            WHERE sha256 = ?
        """
        params: list[object] = [normalized]

        if not include_deleted:
            query += " AND status != ?"
            params.append(AttachmentStatus.DELETED.value)

        query += " ORDER BY created_at ASC, id ASC"

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()

        return [self._row_to_attachment(row) for row in rows]

    def _row_to_attachment(self, row: sqlite3.Row) -> Attachment:
        return Attachment.model_validate(
            {
                "id": row["id"],
                "original_filename": row["original_filename"],
                "object_key": row["object_key"],
                "declared_mime_type": row["declared_mime_type"],
                "inferred_mime_type": row["inferred_mime_type"],
                "size_bytes": row["size_bytes"],
                "sha256": row["sha256"],
                "source_type": AttachmentSourceType(row["source_type"]),
                "status": AttachmentStatus(row["status"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
        )
