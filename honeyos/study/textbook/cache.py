"""Section text cache (L4) with a hard size budget and LRU pruning.

Layout::

    <root>/books/<book_id>/sections/<section_id>.md    extracted text
    <root>/books/<book_id>/sections/<section_id>.json  lifecycle metadata
    <root>/temp/                                       screenshots (purged)
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from hashlib import sha256

from .index_store import check_book_id

DEFAULT_MAX_BYTES = int(os.environ.get("HONEYOS_TEXTBOOK_MAX_BYTES", str(300 * 1024 * 1024)))
MAX_SECTION_BYTES = int(os.environ.get("HONEYOS_TEXTBOOK_MAX_SECTION_BYTES", str(2 * 1024 * 1024)))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TextbookCacheError(RuntimeError):
    pass


@dataclass
class SectionRecord:
    book_id: str
    section_id: str
    title: str
    path: list[str] = field(default_factory=list)
    sha256: str = ""
    text_bytes: int = 0
    created_at: str = field(default_factory=_now)
    last_used_at: str = field(default_factory=_now)
    source: str = "adb_ocr"
    resource_id: str = ""
    screens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SectionRecord":
        return cls(
            book_id=str(raw["book_id"]),
            section_id=str(raw["section_id"]),
            title=str(raw.get("title") or ""),
            path=[str(item) for item in raw.get("path") or []],
            sha256=str(raw.get("sha256") or ""),
            text_bytes=int(raw.get("text_bytes") or 0),
            created_at=str(raw.get("created_at") or _now()),
            last_used_at=str(raw.get("last_used_at") or _now()),
            source=str(raw.get("source") or "adb_ocr"),
            resource_id=str(raw.get("resource_id") or ""),
            screens=int(raw.get("screens") or 0),
        )


class SectionCache:
    def __init__(self, root: Path | str, *, max_bytes: int | None = None):
        self.root = Path(root).expanduser()
        self.max_bytes = int(max_bytes if max_bytes is not None else DEFAULT_MAX_BYTES)

    # -- paths ---------------------------------------------------------
    def sections_dir(self, book_id: str) -> Path:
        return self.root / "books" / check_book_id(book_id) / "sections"

    def text_path(self, book_id: str, section_id: str) -> Path:
        return self.sections_dir(book_id) / f"{self._safe_id(section_id)}.md"

    def meta_path(self, book_id: str, section_id: str) -> Path:
        return self.sections_dir(book_id) / f"{self._safe_id(section_id)}.json"

    @property
    def temp_dir(self) -> Path:
        return self.root / "temp"

    @staticmethod
    def _safe_id(section_id: str) -> str:
        value = str(section_id or "")
        if not value or any(ch in value for ch in ("/", "\\", "..", ":")):
            raise ValueError("无效的章节编号")
        return value

    # -- read/write ----------------------------------------------------
    def has(self, book_id: str, section_id: str) -> bool:
        return self.text_path(book_id, section_id).is_file()

    def write(
        self,
        *,
        book_id: str,
        section_id: str,
        title: str,
        path: list[str] | tuple[str, ...],
        text: str,
        resource_id: str = "",
        screens: int = 0,
        source: str = "adb_ocr",
    ) -> SectionRecord:
        body = str(text or "").strip()
        if not body:
            raise TextbookCacheError("章节正文为空，未写入缓存。")
        size = len(body.encode("utf-8"))
        if size > MAX_SECTION_BYTES:
            raise TextbookCacheError("单节正文超过缓存上限，请拆分章节后再采集。")
        target = self.text_path(book_id, section_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".md.tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(target)
        record = SectionRecord(
            book_id=book_id,
            section_id=section_id,
            title=title,
            path=list(path),
            sha256=sha256(body.encode("utf-8")).hexdigest(),
            text_bytes=size,
            source=source,
            resource_id=resource_id,
            screens=int(screens),
        )
        self._write_meta(record)
        return record

    def _write_meta(self, record: SectionRecord) -> None:
        path = self.meta_path(record.book_id, record.section_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def meta(self, book_id: str, section_id: str) -> SectionRecord | None:
        try:
            raw = json.loads(self.meta_path(book_id, section_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return SectionRecord.from_dict(raw)
        except (KeyError, TypeError, ValueError):
            return None

    def read(self, book_id: str, section_id: str) -> tuple[SectionRecord, str]:
        path = self.text_path(book_id, section_id)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise TextbookCacheError("该章节还没有采集正文。") from exc
        record = self.meta(book_id, section_id)
        if record is None:
            record = SectionRecord(book_id=book_id, section_id=section_id, title=section_id)
        record.last_used_at = _now()
        record.text_bytes = len(text.encode("utf-8"))
        self._write_meta(record)
        return record, text

    def touch(self, book_id: str, section_id: str) -> None:
        record = self.meta(book_id, section_id)
        if record is not None:
            record.last_used_at = _now()
            self._write_meta(record)

    def set_resource(self, book_id: str, section_id: str, resource_id: str) -> None:
        record = self.meta(book_id, section_id)
        if record is None:
            return
        record.resource_id = str(resource_id or "")
        self._write_meta(record)

    def delete(self, book_id: str, section_id: str) -> bool:
        removed = False
        for path in (self.text_path(book_id, section_id), self.meta_path(book_id, section_id)):
            try:
                path.unlink()
                removed = True
            except FileNotFoundError:
                continue
        return removed

    def delete_sections(self, book_id: str, section_ids: list[str]) -> int:
        return sum(1 for section_id in dict.fromkeys(section_ids) if self.delete(book_id, section_id))

    def records(self, book_id: str | None = None) -> list[SectionRecord]:
        base = self.root / "books"
        if not base.is_dir():
            return []
        books = [base / book_id] if book_id else [item for item in base.iterdir() if item.is_dir()]
        rows: list[SectionRecord] = []
        for directory in books:
            sections = directory / "sections"
            if not sections.is_dir():
                continue
            for meta in sections.glob("*.json"):
                try:
                    rows.append(SectionRecord.from_dict(json.loads(meta.read_text(encoding="utf-8"))))
                except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
        return rows

    def stats(self) -> dict[str, Any]:
        rows = self.records()
        total = sum(record.text_bytes for record in rows)
        return {
            "root": str(self.root),
            "sections": len(rows),
            "text_bytes": total,
            "temp_bytes": _dir_size(self.temp_dir),
            "max_bytes": self.max_bytes,
            "books": len({record.book_id for record in rows}),
        }

    def prune(self, *, max_bytes: int | None = None, ttl_days: float | None = None) -> dict[str, Any]:
        budget = int(max_bytes if max_bytes is not None else self.max_bytes)
        rows = self.records()
        removed = 0
        freed = 0
        cutoff = time.time() - float(ttl_days) * 86400 if ttl_days else None
        for record in rows:
            if cutoff is None or _parse_ts(record.last_used_at) >= cutoff:
                continue
            if self.delete(record.book_id, record.section_id):
                removed += 1
                freed += record.text_bytes
        rows = self.records()
        total = sum(record.text_bytes for record in rows)
        if total > budget:
            for record in sorted(rows, key=lambda item: _parse_ts(item.last_used_at)):
                if total <= budget:
                    break
                if self.delete(record.book_id, record.section_id):
                    removed += 1
                    freed += record.text_bytes
                    total -= record.text_bytes
        self.remove_empty_book_dirs()
        return {"removed_sections": removed, "freed_bytes": freed, "stats": self.stats()}

    def remove_empty_book_dirs(self) -> int:
        base = self.root / "books"
        removed = 0
        if not base.is_dir():
            return removed
        for directory in sorted(base.iterdir()):
            if not directory.is_dir():
                continue
            sections = directory / "sections"
            if sections.is_dir() and any(sections.iterdir()):
                continue
            if not (directory / "index.json").exists():
                shutil.rmtree(directory, ignore_errors=True)
                removed += 1
        return removed

    def purge_temp(self, *, older_than_seconds: float = 0) -> dict[str, Any]:
        temp = self.temp_dir
        if not temp.is_dir():
            return {"removed_files": 0, "freed_bytes": 0}
        cutoff = time.time() - max(0.0, float(older_than_seconds))
        removed = 0
        freed = 0
        for item in temp.rglob("*"):
            if not item.is_file():
                continue
            try:
                info = item.stat()
                if info.st_mtime <= cutoff:
                    item.unlink()
                    removed += 1
                    freed += info.st_size
            except OSError:
                continue
        return {"removed_files": removed, "freed_bytes": freed}


def _parse_ts(value: str) -> float:
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _dir_size(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total
