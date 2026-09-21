from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import BinaryIO

from honeyos.files.models import (
    Attachment,
    AttachmentCreateRequest,
    AttachmentStatus,
)
from honeyos.files.repository import (
    AttachmentNotFoundError,
    AttachmentRepository,
)
from honeyos.files.storage import AttachmentStorage
from honeyos.files.validation import (
    DEFAULT_MAX_ATTACHMENT_BYTES,
    AttachmentValidationError,
    validate_attachment_size,
    validate_create_request,
)


class AttachmentServiceError(RuntimeError):
    pass


class AttachmentTooLargeError(AttachmentServiceError):
    pass


class AttachmentService:
    """Application service coordinating attachment metadata and object storage."""

    def __init__(
        self,
        root: Path | str,
        *,
        max_attachment_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES,
    ):
        self.root = Path(root).expanduser().resolve()
        self.max_attachment_bytes = max_attachment_bytes

        self.storage = AttachmentStorage(self.root)
        self.repository = AttachmentRepository(self.root)

    def initialize(self) -> None:
        self.storage.ensure_layout()
        self.repository.initialize()

    def upload_bytes(
        self,
        data: bytes,
        *,
        original_filename: str,
        declared_mime_type: str = "",
        source_type: str = "upload",
    ) -> Attachment:
        request = validate_create_request(
            AttachmentCreateRequest(
                original_filename=original_filename,
                declared_mime_type=declared_mime_type,
                source_type=source_type,
            )
        )

        try:
            validate_attachment_size(
                len(data),
                max_bytes=self.max_attachment_bytes,
            )
        except AttachmentValidationError as exc:
            raise AttachmentTooLargeError(str(exc)) from exc

        object_key, sha256, size_bytes, object_created = (
            self.storage.store_bytes(data)
        )

        attachment = self._build_attachment(
            request=request,
            object_key=object_key,
            sha256=sha256,
            size_bytes=size_bytes,
        )

        try:
            return self.repository.save(attachment)
        except Exception:
            if object_created:
                self._remove_object_if_unreferenced(object_key)
            raise

    def upload_fileobj(
        self,
        fileobj: BinaryIO,
        *,
        original_filename: str,
        declared_mime_type: str = "",
        source_type: str = "upload",
    ) -> Attachment:
        request = validate_create_request(
            AttachmentCreateRequest(
                original_filename=original_filename,
                declared_mime_type=declared_mime_type,
                source_type=source_type,
            )
        )

        try:
            object_key, sha256, size_bytes, object_created = (
                self.storage.store_fileobj(
                    fileobj,
                    max_bytes=self.max_attachment_bytes,
                )
            )
        except Exception as exc:
            from honeyos.files.storage import AttachmentStorageError

            if isinstance(exc, AttachmentStorageError) and (
                "exceeds maximum size" in str(exc)
            ):
                raise AttachmentTooLargeError(str(exc)) from exc
            raise

        attachment = self._build_attachment(
            request=request,
            object_key=object_key,
            sha256=sha256,
            size_bytes=size_bytes,
        )

        try:
            return self.repository.save(attachment)
        except Exception:
            if object_created:
                self._remove_object_if_unreferenced(object_key)
            raise

    def get(self, attachment_id: str) -> Attachment:
        return self.repository.get(attachment_id)

    def list(
        self,
        *,
        include_deleted: bool = False,
    ) -> list[Attachment]:
        return self.repository.list(include_deleted=include_deleted)

    def read_bytes(self, attachment_id: str) -> bytes:
        attachment = self.repository.get(attachment_id)

        if attachment.status == AttachmentStatus.DELETED:
            raise AttachmentServiceError(
                f"attachment {attachment_id!r} is deleted"
            )

        return self.storage.read_bytes(attachment.object_key)

    def soft_delete(self, attachment_id: str) -> Attachment:
        return self.repository.soft_delete(attachment_id)

    def restore(self, attachment_id: str) -> Attachment:
        attachment = self.repository.get(attachment_id)

        if not self.storage.has_object(attachment.object_key):
            raise AttachmentServiceError(
                "cannot restore attachment because its stored object is missing"
            )

        return self.repository.restore(attachment_id)

    def hard_delete(self, attachment_id: str) -> Attachment:
        attachment = self.repository.hard_delete(attachment_id)

        self._remove_object_if_unreferenced(attachment.object_key)

        return attachment

    def _build_attachment(
        self,
        *,
        request: AttachmentCreateRequest,
        object_key: str,
        sha256: str,
        size_bytes: int,
    ) -> Attachment:
        inferred_mime_type = self._detect_mime_from_filename(
            request.original_filename
        )

        return Attachment(
            id=f"att_{uuid.uuid4().hex}",
            original_filename=request.original_filename,
            object_key=object_key,
            declared_mime_type=request.declared_mime_type,
            inferred_mime_type=inferred_mime_type,
            size_bytes=size_bytes,
            sha256=sha256,
            source_type=request.source_type,
            status=AttachmentStatus.READY,
        )

    def _remove_object_if_unreferenced(self, object_key: str) -> bool:
        references = self.repository.count_object_references(
            object_key,
            include_deleted=True,
        )

        if references > 0:
            return False

        return self.storage.delete_object(object_key)

    @staticmethod
    def _detect_mime_from_filename(filename: str) -> str:
        mime_type, _ = mimetypes.guess_type(filename)
        return (mime_type or "").lower()
