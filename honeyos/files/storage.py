from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import BinaryIO, Iterable


DEFAULT_CHUNK_SIZE = 1024 * 1024


class AttachmentStorageError(RuntimeError):
    pass


class AttachmentObjectNotFoundError(FileNotFoundError):
    pass


def canonical_object_key(sha256: str) -> str:
    normalized = str(sha256 or "").strip().lower()

    if len(normalized) != 64:
        raise AttachmentStorageError(
            "sha256 must contain exactly 64 hexadecimal characters"
        )

    if any(ch not in "0123456789abcdef" for ch in normalized):
        raise AttachmentStorageError(
            "sha256 must contain only hexadecimal characters"
        )

    return f"sha256/{normalized[:2]}/{normalized[2:4]}/{normalized}"


def _safe_object_path(objects_root: Path, object_key: str) -> Path:
    root = objects_root.resolve()

    candidate = (root / object_key).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AttachmentStorageError(
            "object_key resolves outside attachment object root"
        ) from exc

    return candidate


class AttachmentStorage:
    """Durable content-addressed object storage for HoneyOS attachments."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.objects_root = self.root / "objects"

    def ensure_layout(self) -> None:
        self.objects_root.mkdir(parents=True, exist_ok=True)

    def object_path(self, object_key: str) -> Path:
        return _safe_object_path(self.objects_root, object_key)

    def has_object(self, object_key: str) -> bool:
        return self.object_path(object_key).is_file()

    def delete_object(self, object_key: str) -> bool:
        path = self.object_path(object_key)

        try:
            path.unlink()
        except FileNotFoundError:
            return False

        self._cleanup_empty_parents(path.parent)
        return True

    def open_object(self, object_key: str, mode: str = "rb"):
        if mode not in {"rb"}:
            raise AttachmentStorageError("attachments may only be opened read-only")

        path = self.object_path(object_key)

        if not path.is_file():
            raise AttachmentObjectNotFoundError(object_key)

        return path.open(mode)

    def read_bytes(self, object_key: str) -> bytes:
        with self.open_object(object_key) as handle:
            return handle.read()

    def store_bytes(self, data: bytes) -> tuple[str, str, int, bool]:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")

        raw = bytes(data)

        digest = hashlib.sha256(raw).hexdigest()
        object_key = canonical_object_key(digest)

        created = self._write_if_missing(
            object_key=object_key,
            chunks=(raw,),
        )

        return object_key, digest, len(raw), created

    def store_fileobj(
        self,
        fileobj: BinaryIO,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        max_bytes: int | None = None,
    ) -> tuple[str, str, int, bool]:
        if chunk_size <= 0:
            raise AttachmentStorageError("chunk_size must be positive")

        if max_bytes is not None and max_bytes < 0:
            raise AttachmentStorageError("max_bytes must not be negative")

        self.ensure_layout()

        hasher = hashlib.sha256()
        size_bytes = 0

        temp_fd, temp_name = tempfile.mkstemp(
            prefix=".upload-",
            suffix=".tmp",
            dir=self.root,
        )

        try:
            with os.fdopen(temp_fd, "wb") as temp_file:
                while True:
                    chunk = fileobj.read(chunk_size)

                    if not chunk:
                        break

                    if not isinstance(chunk, (bytes, bytearray, memoryview)):
                        raise AttachmentStorageError(
                            "file object must return bytes"
                        )

                    raw = bytes(chunk)

                    if (
                        max_bytes is not None
                        and size_bytes + len(raw) > max_bytes
                    ):
                        raise AttachmentStorageError(
                            f"attachment exceeds maximum size of {max_bytes} bytes"
                        )

                    hasher.update(raw)
                    size_bytes += len(raw)
                    temp_file.write(raw)

                temp_file.flush()
                os.fsync(temp_file.fileno())

            digest = hasher.hexdigest()
            object_key = canonical_object_key(digest)
            final_path = self.object_path(object_key)

            if final_path.exists():
                Path(temp_name).unlink(missing_ok=True)
                return object_key, digest, size_bytes, False

            final_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                os.replace(temp_name, final_path)
            except OSError as exc:
                raise AttachmentStorageError(
                    f"failed to persist attachment object: {exc}"
                ) from exc

            return object_key, digest, size_bytes, True

        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

    def _write_if_missing(
        self,
        *,
        object_key: str,
        chunks: Iterable[bytes],
    ) -> bool:
        self.ensure_layout()

        final_path = self.object_path(object_key)

        if final_path.exists():
            return False

        final_path.parent.mkdir(parents=True, exist_ok=True)

        temp_fd, temp_name = tempfile.mkstemp(
            prefix=".object-",
            suffix=".tmp",
            dir=final_path.parent,
        )

        try:
            with os.fdopen(temp_fd, "wb") as temp_file:
                for chunk in chunks:
                    temp_file.write(chunk)

                temp_file.flush()
                os.fsync(temp_file.fileno())

            if final_path.exists():
                Path(temp_name).unlink(missing_ok=True)
                return False

            os.replace(temp_name, final_path)

        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

        return True

    def _cleanup_empty_parents(self, start: Path) -> None:
        current = start
        stop = self.objects_root.resolve()

        while current != stop:
            try:
                current.rmdir()
            except OSError:
                break

            current = current.parent
