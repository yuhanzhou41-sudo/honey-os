from __future__ import annotations

from contextlib import nullcontext
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StudyLibraryIndexError(RuntimeError):
    pass


class StudyLibraryIndex:
    """Derived searchable StudyResource content stored in canonical study.db."""

    MAX_QUERY_CHARS = 2048

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS study_resource_content (
                    resource_id TEXT PRIMARY KEY
                        REFERENCES study_resources(id) ON DELETE CASCADE,
                    extracted_text TEXT NOT NULL DEFAULT '',
                    extraction_kind TEXT NOT NULL DEFAULT 'utf8_text',
                    indexed_at TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS study_resource_fts USING fts5(
                    resource_id UNINDEXED,
                    title,
                    course_or_subject,
                    content,
                    tokenize='unicode61'
                );
            """)

    @classmethod
    def _fts_query(cls, query: str) -> str:
        raw=(query or "")[:cls.MAX_QUERY_CHARS].strip()
        if not raw:
            return ""
        tokens=[t for t in re.split(r"\s+", raw) if t]
        return " OR ".join('"'+t.replace('"','""')+'"' for t in tokens)

    def index_resource(self, *, resource_id: str, title: str, course_or_subject: str, content: str, extraction_kind: str='utf8_text', connection=None) -> None:
        stamp=datetime.now(timezone.utc).isoformat()
        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            conn.execute("""
                INSERT INTO study_resource_content(resource_id, extracted_text, extraction_kind, indexed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                    extracted_text=excluded.extracted_text,
                    extraction_kind=excluded.extraction_kind,
                    indexed_at=excluded.indexed_at
            """, (resource_id, content, extraction_kind, stamp))
            conn.execute("DELETE FROM study_resource_fts WHERE resource_id = ?", (resource_id,))
            conn.execute("""
                INSERT INTO study_resource_fts(resource_id, title, course_or_subject, content)
                VALUES (?, ?, ?, ?)
            """, (resource_id, title, course_or_subject, content))

    def update_resource_metadata(self, *, resource_id: str, title: str, course_or_subject: str) -> None:
        with self._connect() as conn:
            row=conn.execute("SELECT extracted_text FROM study_resource_content WHERE resource_id = ?", (resource_id,)).fetchone()
        if row is not None:
            self.index_resource(resource_id=resource_id, title=title, course_or_subject=course_or_subject, content=row['extracted_text'])

    def delete_resource(self, resource_id: str, *, connection=None) -> None:
        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            conn.execute("DELETE FROM study_resource_fts WHERE resource_id = ?", (resource_id,))
            conn.execute("DELETE FROM study_resource_content WHERE resource_id = ?", (resource_id,))

    def get_content(self, resource_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row=conn.execute("SELECT extracted_text, extraction_kind, indexed_at FROM study_resource_content WHERE resource_id = ?", (resource_id,)).fetchone()
        return dict(row) if row is not None else None

    def search(self, *, query: str='', course_or_subject: str='', resource_type: str='', limit: int=20) -> list[dict[str, Any]]:
        limit=max(1,min(int(limit),100))
        fts=self._fts_query(query)
        where=[]; params=[]
        if fts:
            where.append("study_resource_fts MATCH ?"); params.append(fts)
        if course_or_subject:
            where.append("r.course_or_subject = ?"); params.append(course_or_subject)
        if resource_type:
            where.append("r.resource_type = ?"); params.append(resource_type)
        sql="""
            SELECT r.id AS resource_id, r.attachment_id, r.title, r.resource_type,
                   r.course_or_subject, r.metadata_json,
                   CASE WHEN ? THEN snippet(study_resource_fts, 3, '>>>', '<<<', '…', 24)
                        ELSE substr(c.extracted_text, 1, 400) END AS snippet
            FROM study_resources AS r
            JOIN study_resource_content AS c ON c.resource_id = r.id
            JOIN study_resource_fts ON study_resource_fts.resource_id = r.id
        """
        sql_params=[1 if fts else 0]
        if where: sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY " + ("bm25(study_resource_fts), " if fts else "") + "r.updated_at DESC, r.id ASC LIMIT ?"
        sql_params.extend(params); sql_params.append(limit)
        with self._connect() as conn:
            rows=conn.execute(sql, tuple(sql_params)).fetchall()
        return [{
            'resource_id':r['resource_id'], 'attachment_id':r['attachment_id'], 'title':r['title'],
            'resource_type':r['resource_type'], 'course_or_subject':r['course_or_subject'],
            'metadata':json.loads(r['metadata_json'] or '{}'), 'snippet':r['snippet'] or ''
        } for r in rows]
