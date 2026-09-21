import pytest
from pydantic import ValidationError

from honeyos.files.models import (
    Attachment,
    AttachmentSourceType,
    AttachmentStatus,
)


VALID_SHA = "a" * 64
VALID_KEY = f"sha256/{VALID_SHA[:2]}/{VALID_SHA[2:4]}/{VALID_SHA}"


def test_attachment_defaults():
    attachment = Attachment(
        id="att_test",
        original_filename="notes.pdf",
        object_key=VALID_KEY,
        size_bytes=123,
        sha256=VALID_SHA,
    )

    assert attachment.source_type == AttachmentSourceType.UPLOAD
    assert attachment.status == AttachmentStatus.READY
    assert attachment.declared_mime_type == ""
    assert attachment.inferred_mime_type == ""


def test_attachment_normalizes_sha_and_mime():
    attachment = Attachment(
        id="att_test",
        original_filename="notes.pdf",
        object_key=VALID_KEY,
        declared_mime_type=" Application/PDF ",
        inferred_mime_type=" APPLICATION/PDF ",
        size_bytes=123,
        sha256="A" * 64,
    )

    assert attachment.sha256 == "a" * 64
    assert attachment.declared_mime_type == "application/pdf"
    assert attachment.inferred_mime_type == "application/pdf"


def test_attachment_rejects_invalid_sha256():
    with pytest.raises(ValidationError):
        Attachment(
            id="att_test",
            original_filename="notes.pdf",
            object_key="x",
            size_bytes=123,
            sha256="not-a-sha256",
        )


def test_attachment_rejects_extra_fields():
    with pytest.raises(ValidationError):
        Attachment(
            id="att_test",
            original_filename="notes.pdf",
            object_key=VALID_KEY,
            size_bytes=123,
            sha256=VALID_SHA,
            unexpected=True,
        )
