from __future__ import annotations

import re
from pathlib import PurePath

from honeyos.files.models import Attachment, AttachmentCreateRequest


DEFAULT_MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


class AttachmentValidationError(ValueError):
    pass


def sanitize_display_filename(filename: str) -> str:
    """Return a safe display filename without using it as a storage path.

    This intentionally strips directory components and control characters.
    The returned value is metadata only. Durable storage must use object_key.
    """

    raw = str(filename or "").strip()
    if not raw:
        raise AttachmentValidationError("filename must not be blank")

    normalized = raw.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    basename = _CONTROL_CHAR_RE.sub("", basename).strip()

    if basename in {"", ".", ".."}:
        raise AttachmentValidationError("filename is invalid")

    if len(basename) > 500:
        raise AttachmentValidationError("filename exceeds 500 characters")

    return basename


def validate_attachment_size(
    size_bytes: int,
    *,
    max_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES,
) -> int:
    try:
        size = int(size_bytes)
    except (TypeError, ValueError) as exc:
        raise AttachmentValidationError("size_bytes must be an integer") from exc

    if size < 0:
        raise AttachmentValidationError("size_bytes must not be negative")

    if size > max_bytes:
        raise AttachmentValidationError(
            f"attachment exceeds maximum size of {max_bytes} bytes"
        )

    return size


def validate_object_key(object_key: str, sha256: str) -> str:
    """Require the canonical content-addressed object-key layout."""

    expected = f"sha256/{sha256[:2]}/{sha256[2:4]}/{sha256}"

    if object_key != expected:
        raise AttachmentValidationError(
            f"object_key must equal canonical SHA-256 path {expected!r}"
        )

    return object_key


def validate_create_request(
    request: AttachmentCreateRequest | dict,
) -> AttachmentCreateRequest:
    if not isinstance(request, AttachmentCreateRequest):
        request = AttachmentCreateRequest.model_validate(request)

    safe_name = sanitize_display_filename(request.original_filename)

    if safe_name != request.original_filename:
        request = request.model_copy(
            update={"original_filename": safe_name},
        )

    return request


def validate_attachment(
    attachment: Attachment | dict,
    *,
    max_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES,
) -> Attachment:
    if not isinstance(attachment, Attachment):
        attachment = Attachment.model_validate(attachment)

    safe_name = sanitize_display_filename(attachment.original_filename)
    validate_attachment_size(attachment.size_bytes, max_bytes=max_bytes)
    validate_object_key(attachment.object_key, attachment.sha256)

    if safe_name != attachment.original_filename:
        attachment = attachment.model_copy(
            update={"original_filename": safe_name},
        )

    return attachment
