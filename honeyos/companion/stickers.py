"""C1.2 local sticker runtime.

Original media stays on disk. A small static WebP preview is generated for the picker,
so browsing the sticker library does not decode every animated GIF at once.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image

STICKER_LIMIT = 400
STICKER_WARNING_THRESHOLD = 360
MAX_STICKER_BYTES = 15 * 1024 * 1024
MAX_STICKER_PIXELS = 16_000_000
PREVIEW_EDGE = 160

STICKER_REACTIONS = {
    "happy", "laugh", "love", "shy", "comfort", "hug", "sad", "cry",
    "angry", "annoyed", "shock", "confused", "awkward", "sleepy",
    "cheer", "celebrate",
}

_MIME_BY_EXT = {
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".png": "image/png",
}

_FORMAT_BY_EXT = {
    ".gif": "GIF",
    ".webp": "WEBP",
    ".png": "PNG",
}


class StickerError(RuntimeError):
    pass


class StickerLimitReached(StickerError):
    pass


class StickerValidationError(StickerError):
    pass


def default_sticker_root() -> Path:
    configured = os.environ.get("HONEYOS_STICKER_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    if Path("/mnt/d").exists():
        return Path("/mnt/d/HoneyOS-Data/stickers")
    return Path.home() / ".honeyos" / "companion" / "stickers"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _detected_extension(path: Path) -> str | None:
    with path.open("rb") as handle:
        head = handle.read(16)
    if head.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    return None


def _validate_decodable_image(path: Path, extension: str) -> None:
    try:
        with Image.open(path) as image:
            expected = _FORMAT_BY_EXT[extension]
            if str(image.format or "").upper() != expected:
                raise StickerValidationError("sticker_file_type_invalid")
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_STICKER_PIXELS:
                raise StickerValidationError("sticker_dimensions_invalid")
            image.seek(0)
            image.load()
    except StickerValidationError:
        raise
    except Exception as exc:
        raise StickerValidationError("sticker_file_type_invalid") from exc


class StickerStore:
    def __init__(
        self,
        root: Path | None = None,
        *,
        limit: int = STICKER_LIMIT,
        warning_threshold: int = STICKER_WARNING_THRESHOLD,
        max_file_bytes: int = MAX_STICKER_BYTES,
    ) -> None:
        self.root = (root or default_sticker_root()).expanduser()
        self.files_dir = self.root / "files"
        self.previews_dir = self.root / "previews"
        self.manifest_path = self.root / "index.json"
        self.limit = int(limit)
        self.warning_threshold = min(int(warning_threshold), self.limit)
        self.max_file_bytes = int(max_file_bytes)
        self._lock = threading.RLock()
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.previews_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._write({"version": 1, "stickers": []})

    def _read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StickerError("sticker_manifest_unreadable") from exc
        stickers = raw.get("stickers")
        if not isinstance(stickers, list):
            raise StickerError("sticker_manifest_invalid")
        return {"version": 1, "stickers": stickers}

    def _write(self, payload: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        tmp = self.root / f".index-{uuid4().hex}.tmp"
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp, self.manifest_path)

    def _create_preview(self, source: Path, sticker_id: str) -> str | None:
        preview_name = f"{sticker_id}.webp"
        preview_path = self.previews_dir / preview_name
        try:
            with Image.open(source) as image:
                image.seek(0)
                frame = image.convert("RGBA")
                frame.thumbnail((PREVIEW_EDGE, PREVIEW_EDGE), Image.Resampling.LANCZOS)
                frame.save(preview_path, format="WEBP", quality=82, method=4)
            return preview_name
        except Exception:
            try:
                preview_path.unlink()
            except FileNotFoundError:
                pass
            return None

    def status(self) -> dict[str, Any]:
        with self._lock:
            items = self._read()["stickers"]
            count = len(items)
            total_bytes = sum(int(item.get("size_bytes") or 0) for item in items)
            return {
                "count": count,
                "limit": self.limit,
                "warning_threshold": self.warning_threshold,
                "warning": count >= self.warning_threshold,
                "full": count >= self.limit,
                "total_bytes": total_bytes,
                "storage_root": str(self.root),
            }

    def list(
        self,
        *,
        tag: str | None = None,
        sort: str = "recent",
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._read()["stickers"])
        if tag:
            items = [item for item in items if tag in (item.get("tags") or [])]
        if sort == "least_used":
            items.sort(
                key=lambda item: (
                    int(item.get("usage_count") or 0),
                    str(item.get("last_used_at") or ""),
                    str(item.get("created_at") or ""),
                )
            )
        elif sort == "largest":
            items.sort(
                key=lambda item: int(item.get("size_bytes") or 0),
                reverse=True,
            )
        else:
            items.sort(
                key=lambda item: str(item.get("created_at") or ""),
                reverse=True,
            )
        return items[: max(1, min(int(limit), 60))]

    def add_file(
        self,
        source: Path,
        *,
        original_name: str,
        tag: str,
    ) -> dict[str, Any]:
        tag = str(tag or "").strip()
        if tag not in STICKER_REACTIONS:
            raise StickerValidationError("sticker_tag_invalid")

        size = source.stat().st_size
        if size <= 0 or size > self.max_file_bytes:
            raise StickerValidationError("sticker_file_size_invalid")

        detected = _detected_extension(source)
        requested = Path(original_name or "").suffix.lower()
        if detected is None or requested not in _MIME_BY_EXT or detected != requested:
            raise StickerValidationError("sticker_file_type_invalid")
        _validate_decodable_image(source, detected)

        with self._lock:
            manifest = self._read()
            if len(manifest["stickers"]) >= self.limit:
                raise StickerLimitReached("sticker_limit_reached")

            sticker_id = uuid4().hex
            filename = f"{sticker_id}{detected}"
            target = self.files_dir / filename
            shutil.move(str(source), target)
            preview_filename = self._create_preview(target, sticker_id)

            entry = {
                "id": sticker_id,
                "filename": filename,
                "preview_filename": preview_filename,
                "original_name": Path(original_name).name[:180],
                "mime_type": _MIME_BY_EXT[detected],
                "size_bytes": int(size),
                "tags": [tag],
                "created_at": _utc_now(),
                "usage_count": 0,
                "last_used_at": None,
            }
            manifest["stickers"].append(entry)
            self._write(manifest)
            return entry

    def delete(self, sticker_id: str) -> bool:
        with self._lock:
            manifest = self._read()
            match = next(
                (item for item in manifest["stickers"] if item.get("id") == sticker_id),
                None,
            )
            if not match:
                return False
            manifest["stickers"] = [
                item for item in manifest["stickers"]
                if item.get("id") != sticker_id
            ]
            self._write(manifest)

            for directory, key in (
                (self.files_dir, "filename"),
                (self.previews_dir, "preview_filename"),
            ):
                filename = str(match.get(key) or "")
                if not filename:
                    continue
                try:
                    (directory / filename).unlink()
                except FileNotFoundError:
                    pass
            return True

    def mark_used(self, sticker_id: str) -> dict[str, Any] | None:
        with self._lock:
            manifest = self._read()
            target = next(
                (item for item in manifest["stickers"] if item.get("id") == sticker_id),
                None,
            )
            if not target:
                return None
            target["usage_count"] = int(target.get("usage_count") or 0) + 1
            target["last_used_at"] = _utc_now()
            self._write(manifest)
            return target

    def media(self, sticker_id: str) -> tuple[Path, str] | None:
        with self._lock:
            item = next(
                (item for item in self._read()["stickers"] if item.get("id") == sticker_id),
                None,
            )
        if not item:
            return None
        path = self.files_dir / str(item.get("filename") or "")
        try:
            path.resolve().relative_to(self.files_dir.resolve())
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path, str(item.get("mime_type") or "application/octet-stream")

    def preview(self, sticker_id: str) -> tuple[Path, str] | None:
        with self._lock:
            manifest = self._read()
            item = next(
                (entry for entry in manifest["stickers"] if entry.get("id") == sticker_id),
                None,
            )
            if not item:
                return None

            preview_name = str(item.get("preview_filename") or "")
            preview_path = self.previews_dir / preview_name if preview_name else None
            if preview_path is None or not preview_path.is_file():
                media_path = self.files_dir / str(item.get("filename") or "")
                if not media_path.is_file():
                    return None
                preview_name = self._create_preview(media_path, sticker_id) or ""
                if not preview_name:
                    return None
                item["preview_filename"] = preview_name
                self._write(manifest)
                preview_path = self.previews_dir / preview_name

        try:
            preview_path.resolve().relative_to(self.previews_dir.resolve())
        except ValueError:
            return None
        if not preview_path.is_file():
            return None
        return preview_path, "image/webp"


@lru_cache(maxsize=1)
def get_sticker_store() -> StickerStore:
    return StickerStore()
