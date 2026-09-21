import hashlib
import io

import pytest

from honeyos.files.storage import (
    AttachmentObjectNotFoundError,
    AttachmentStorage,
    AttachmentStorageError,
    canonical_object_key,
)


def test_canonical_object_key():
    digest = "0123456789abcdef" * 4

    assert canonical_object_key(digest) == (
        f"sha256/{digest[:2]}/{digest[2:4]}/{digest}"
    )


def test_canonical_object_key_rejects_invalid_sha():
    with pytest.raises(AttachmentStorageError):
        canonical_object_key("bad")


def test_store_bytes_creates_content_addressed_object(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    payload = b"hello honeyos"
    expected_sha = hashlib.sha256(payload).hexdigest()

    object_key, sha256, size_bytes, created = storage.store_bytes(payload)

    assert sha256 == expected_sha
    assert size_bytes == len(payload)
    assert created is True
    assert object_key == canonical_object_key(expected_sha)

    path = storage.object_path(object_key)

    assert path.is_file()
    assert path.read_bytes() == payload


def test_store_bytes_deduplicates_same_content(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    first = storage.store_bytes(b"same content")
    second = storage.store_bytes(b"same content")

    assert first[0] == second[0]
    assert first[1] == second[1]
    assert first[3] is True
    assert second[3] is False


def test_store_fileobj_streams_and_persists(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    payload = b"abc123" * 10000

    object_key, sha256, size_bytes, created = storage.store_fileobj(
        io.BytesIO(payload),
        chunk_size=1024,
    )

    assert created is True
    assert size_bytes == len(payload)
    assert sha256 == hashlib.sha256(payload).hexdigest()
    assert storage.read_bytes(object_key) == payload


def test_store_fileobj_deduplicates_existing_object(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    payload = b"duplicate stream"

    first = storage.store_fileobj(io.BytesIO(payload))
    second = storage.store_fileobj(io.BytesIO(payload))

    assert first[0] == second[0]
    assert first[3] is True
    assert second[3] is False


def test_object_path_rejects_escape(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    with pytest.raises(AttachmentStorageError):
        storage.object_path("../../etc/passwd")


def test_open_missing_object_raises(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    digest = "a" * 64
    object_key = canonical_object_key(digest)

    with pytest.raises(AttachmentObjectNotFoundError):
        storage.open_object(object_key)


def test_delete_object(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    object_key, _, _, _ = storage.store_bytes(b"delete me")

    assert storage.has_object(object_key) is True
    assert storage.delete_object(object_key) is True
    assert storage.has_object(object_key) is False

    assert storage.delete_object(object_key) is False


def test_open_object_is_read_only(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    object_key, _, _, _ = storage.store_bytes(b"hello")

    with pytest.raises(AttachmentStorageError):
        storage.open_object(object_key, "wb")


def test_store_fileobj_stops_at_streaming_size_limit(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    payload = b"x" * 100

    with pytest.raises(
        AttachmentStorageError,
        match="exceeds maximum size",
    ):
        storage.store_fileobj(
            io.BytesIO(payload),
            chunk_size=10,
            max_bytes=25,
        )

    object_files = [
        path
        for path in (tmp_path / "attachments").rglob("*")
        if path.is_file()
    ]

    assert object_files == []


def test_store_fileobj_accepts_exact_size_limit(tmp_path):
    storage = AttachmentStorage(tmp_path / "attachments")

    payload = b"x" * 25

    object_key, _, size_bytes, created = storage.store_fileobj(
        io.BytesIO(payload),
        chunk_size=10,
        max_bytes=25,
    )

    assert size_bytes == 25
    assert created is True
    assert storage.read_bytes(object_key) == payload
