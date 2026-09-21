from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AttachmentSourceType(StrEnum):
    UPLOAD = "upload"
    CHAT = "chat"
    STUDY = "study"
    IMPORT = "import"


class AttachmentStatus(StrEnum):
    READY = "ready"
    DELETED = "deleted"
    FAILED = "failed"


class Attachment(BaseModel):
    """Canonical HoneyOS attachment metadata.

    The actual file bytes live in AttachmentStorage. This model contains only
    stable metadata and never exposes a caller-controlled filesystem path.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=200)

    original_filename: str = Field(min_length=1, max_length=500)
    object_key: str = Field(min_length=1, max_length=1000)

    declared_mime_type: str = Field(default="", max_length=255)
    inferred_mime_type: str = Field(default="", max_length=255)

    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)

    source_type: AttachmentSourceType = AttachmentSourceType.UPLOAD
    status: AttachmentStatus = AttachmentStatus.READY

    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64:
            raise ValueError("sha256 must contain exactly 64 hexadecimal characters")
        if any(ch not in "0123456789abcdef" for ch in normalized):
            raise ValueError("sha256 must contain only hexadecimal characters")
        return normalized

    @field_validator("declared_mime_type", "inferred_mime_type")
    @classmethod
    def normalize_mime_type(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("original_filename")
    @classmethod
    def reject_invalid_filename(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("original_filename must not be blank")
        if "\x00" in stripped:
            raise ValueError("original_filename must not contain NUL bytes")
        return stripped


class AttachmentCreateRequest(BaseModel):
    """Validated metadata supplied before durable storage is created."""

    model_config = ConfigDict(extra="forbid")

    original_filename: str = Field(min_length=1, max_length=500)
    declared_mime_type: str = Field(default="", max_length=255)
    source_type: AttachmentSourceType = AttachmentSourceType.UPLOAD

    @field_validator("original_filename")
    @classmethod
    def reject_invalid_filename(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("original_filename must not be blank")
        if "\x00" in stripped:
            raise ValueError("original_filename must not contain NUL bytes")
        return stripped

    @field_validator("declared_mime_type")
    @classmethod
    def normalize_declared_mime_type(cls, value: str) -> str:
        return value.strip().lower()
