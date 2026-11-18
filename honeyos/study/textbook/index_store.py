"""Persistent chapter index (L1) stored per book as a small JSON file."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .outline import BookOutline, TextbookOutlineError

_BOOK_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TextbookIndexError(RuntimeError):
    pass


class TextbookBookNotFoundError(KeyError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def check_book_id(book_id: str) -> str:
    value = str(book_id or "").strip()
    if not _BOOK_ID.fullmatch(value):
        raise ValueError("教材编号只能使用字母、数字、下划线和短横线，最长 64 位。")
    return value


class TextbookIndexStore:
    """One ``books/<book_id>/index.json`` per textbook; no body text here."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser()

    def book_dir(self, book_id: str) -> Path:
        return self.root / "books" / check_book_id(book_id)

    def index_path(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "index.json"

    def save(self, outline: BookOutline) -> BookOutline:
        path = self.index_path(outline.book_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = outline.to_dict()
        payload["updated_at"] = _now()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return BookOutline.from_dict(payload)

    def load(self, book_id: str) -> BookOutline:
        path = self.index_path(book_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise TextbookBookNotFoundError(book_id) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise TextbookIndexError(f"教材目录索引损坏：{book_id}") from exc
        try:
            return BookOutline.from_dict(raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise TextbookIndexError(f"教材目录索引格式有误：{book_id}") from exc

    def exists(self, book_id: str) -> bool:
        try:
            return self.index_path(book_id).is_file()
        except ValueError:
            return False

    def list_books(self) -> list[dict[str, Any]]:
        base = self.root / "books"
        if not base.is_dir():
            return []
        books: list[dict[str, Any]] = []
        for directory in sorted(base.iterdir()):
            if not directory.is_dir() or not (directory / "index.json").is_file():
                continue
            try:
                outline = self.load(directory.name)
            except (TextbookBookNotFoundError, TextbookIndexError, TextbookOutlineError):
                continue
            books.append(
                {
                    "book_id": outline.book_id,
                    "title": outline.title,
                    "sections": len(outline.sections),
                    "updated_at": outline.updated_at,
                }
            )
        return books

    def delete(self, book_id: str) -> bool:
        directory = self.book_dir(book_id)
        if not directory.is_dir():
            return False
        for child in sorted(directory.rglob("*"), reverse=True):
            try:
                child.unlink() if child.is_file() else child.rmdir()
            except OSError:
                pass
        try:
            directory.rmdir()
        except OSError:
            pass
        return True

    def index_bytes(self) -> int:
        base = self.root / "books"
        total = 0
        if not base.is_dir():
            return 0
        for item in base.rglob("index.json"):
            try:
                total += item.stat().st_size
            except OSError:
                continue
        return total

    def cleanup_empty_dirs(self) -> int:
        base = self.root / "books"
        removed = 0
        if not base.is_dir():
            return removed
        for directory in sorted(base.iterdir(), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                try:
                    directory.rmdir()
                    removed += 1
                except OSError:
                    continue
        return removed

    def disk_usage(self) -> dict[str, int]:
        try:
            import shutil

            usage = shutil.disk_usage(self.root if self.root.exists() else self.root.parent)
            return {"free_bytes": usage.free, "total_bytes": usage.total}
        except OSError:
            return {"free_bytes": 0, "total_bytes": 0}

    def ensure_root(self) -> Path:
        os.makedirs(self.root, exist_ok=True)
        return self.root
