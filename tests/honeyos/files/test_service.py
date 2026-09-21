import io

import pytest

from honeyos.files.models import AttachmentStatus
from honeyos.files.repository import AttachmentNotFoundError
from honeyos.files.service import (
    AttachmentService,
    AttachmentServiceError,
    AttachmentTooLargeError,
)


def test_upload_bytes_round_trip(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    payload = b"hello study system"

    attachment = service.upload_bytes(
        payload,
        original_filename="notes.pdf",
        declared_mime_type="application/pdf",
    )

    assert attachment.id.startswith("att_")
    assert attachment.original_filename == "notes.pdf"
    assert attachment.size_bytes == len(payload)
    assert attachment.declared_mime_type == "application/pdf"
    assert service.read_bytes(attachment.id) == payload


def test_upload_sanitizes_filename(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    attachment = service.upload_bytes(
        b"hello",
        original_filename="../../course/notes.pdf",
    )

    assert attachment.original_filename == "notes.pdf"


def test_upload_fileobj_round_trip(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    payload = b"stream-data" * 1000

    attachment = service.upload_fileobj(
        io.BytesIO(payload),
        original_filename="lecture.pptx",
    )

    assert attachment.size_bytes == len(payload)
    assert service.read_bytes(attachment.id) == payload


def test_duplicate_uploads_share_object(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    first = service.upload_bytes(
        b"same content",
        original_filename="first.pdf",
    )

    second = service.upload_bytes(
        b"same content",
        original_filename="second.pdf",
    )

    assert first.id != second.id
    assert first.object_key == second.object_key
    assert first.sha256 == second.sha256

    assert service.repository.count_object_references(
        first.object_key,
        include_deleted=True,
    ) == 2


def test_soft_delete_preserves_object_and_can_restore(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    attachment = service.upload_bytes(
        b"keep me",
        original_filename="notes.pdf",
    )

    deleted = service.soft_delete(attachment.id)

    assert deleted.status == AttachmentStatus.DELETED
    assert service.storage.has_object(attachment.object_key) is True

    restored = service.restore(attachment.id)

    assert restored.status == AttachmentStatus.READY
    assert service.read_bytes(restored.id) == b"keep me"


def test_read_soft_deleted_attachment_fails(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    attachment = service.upload_bytes(
        b"hidden",
        original_filename="notes.pdf",
    )

    service.soft_delete(attachment.id)

    with pytest.raises(AttachmentServiceError):
        service.read_bytes(attachment.id)


def test_hard_delete_last_reference_removes_object(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    attachment = service.upload_bytes(
        b"remove me",
        original_filename="notes.pdf",
    )

    object_key = attachment.object_key

    service.hard_delete(attachment.id)

    assert service.storage.has_object(object_key) is False

    with pytest.raises(AttachmentNotFoundError):
        service.get(attachment.id)


def test_hard_delete_does_not_remove_shared_object(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    first = service.upload_bytes(
        b"shared",
        original_filename="one.pdf",
    )

    second = service.upload_bytes(
        b"shared",
        original_filename="two.pdf",
    )

    service.hard_delete(first.id)

    assert service.storage.has_object(second.object_key) is True
    assert service.read_bytes(second.id) == b"shared"


def test_soft_deleted_reference_still_protects_object(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    first = service.upload_bytes(
        b"shared",
        original_filename="one.pdf",
    )

    second = service.upload_bytes(
        b"shared",
        original_filename="two.pdf",
    )

    service.soft_delete(first.id)
    service.hard_delete(second.id)

    assert service.storage.has_object(first.object_key) is True

    restored = service.restore(first.id)

    assert service.read_bytes(restored.id) == b"shared"


def test_upload_bytes_rejects_oversize_before_storage(tmp_path):
    service = AttachmentService(
        tmp_path / "attachments",
        max_attachment_bytes=4,
    )

    with pytest.raises(AttachmentTooLargeError):
        service.upload_bytes(
            b"12345",
            original_filename="too-big.txt",
        )

    assert not list(
        (tmp_path / "attachments").glob("objects/**/*")
    )


def test_upload_fileobj_rejects_oversize_and_cleans_object(tmp_path):
    service = AttachmentService(
        tmp_path / "attachments",
        max_attachment_bytes=4,
    )

    with pytest.raises(AttachmentTooLargeError):
        service.upload_fileobj(
            io.BytesIO(b"12345"),
            original_filename="too-big.txt",
        )

    assert service.list(include_deleted=True) == []


def test_restore_fails_if_object_missing(tmp_path):
    service = AttachmentService(tmp_path / "attachments")

    attachment = service.upload_bytes(
        b"hello",
        original_filename="notes.txt",
    )

    service.soft_delete(attachment.id)
    service.storage.delete_object(attachment.object_key)

    with pytest.raises(AttachmentServiceError):
        service.restore(attachment.id)
