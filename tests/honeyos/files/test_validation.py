import pytest

from honeyos.files.models import Attachment, AttachmentCreateRequest
from honeyos.files.validation import (
    AttachmentValidationError,
    sanitize_display_filename,
    validate_attachment,
    validate_attachment_size,
    validate_create_request,
    validate_object_key,
)


VALID_SHA = "0123456789abcdef" * 4
VALID_KEY = f"sha256/{VALID_SHA[:2]}/{VALID_SHA[2:4]}/{VALID_SHA}"


def test_sanitize_display_filename_strips_unix_path():
    assert sanitize_display_filename("../../course/notes.pdf") == "notes.pdf"


def test_sanitize_display_filename_strips_windows_path():
    assert sanitize_display_filename(r"C:\Users\student\notes.pdf") == "notes.pdf"


def test_sanitize_display_filename_rejects_dot_names():
    with pytest.raises(AttachmentValidationError):
        sanitize_display_filename("..")


def test_validate_attachment_size_accepts_boundary():
    assert validate_attachment_size(100, max_bytes=100) == 100


def test_validate_attachment_size_rejects_oversize():
    with pytest.raises(AttachmentValidationError):
        validate_attachment_size(101, max_bytes=100)


def test_validate_object_key_requires_sha_layout():
    assert validate_object_key(VALID_KEY, VALID_SHA) == VALID_KEY

    with pytest.raises(AttachmentValidationError):
        validate_object_key("uploads/notes.pdf", VALID_SHA)


def test_validate_create_request_sanitizes_filename():
    request = validate_create_request(
        AttachmentCreateRequest(
            original_filename="../../notes.pdf",
            declared_mime_type="Application/PDF",
        )
    )

    assert request.original_filename == "notes.pdf"
    assert request.declared_mime_type == "application/pdf"


def test_validate_attachment_checks_semantics():
    attachment = Attachment(
        id="att_test",
        original_filename="../../notes.pdf",
        object_key=VALID_KEY,
        declared_mime_type="application/pdf",
        inferred_mime_type="application/pdf",
        size_bytes=1024,
        sha256=VALID_SHA,
    )

    validated = validate_attachment(attachment)

    assert validated.original_filename == "notes.pdf"
