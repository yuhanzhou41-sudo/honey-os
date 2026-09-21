from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from aiohttp import web

from honeyos.files.models import Attachment
from honeyos.files.repository import AttachmentNotFoundError
from honeyos.files.service import (
    AttachmentService,
    AttachmentServiceError,
    AttachmentTooLargeError,
)


def attachment_to_dict(attachment: Attachment) -> dict[str, Any]:
    return attachment.model_dump(mode="json")


class AttachmentHTTPHandlers:
    """HTTP adapter around AttachmentService.

    This module intentionally knows nothing about chat messages, StudyResource,
    model providers, or file-processing models.
    """

    def __init__(
        self,
        root: Path | str,
        *,
        max_attachment_bytes: int | None = None,
    ):
        kwargs: dict[str, Any] = {}

        if max_attachment_bytes is not None:
            kwargs["max_attachment_bytes"] = max_attachment_bytes

        self.service = AttachmentService(root, **kwargs)

    async def upload(self, request: web.Request) -> web.Response:
        if not request.content_type.startswith("multipart/"):
            return self._error(
                "content_type",
                "multipart/form-data is required",
                status=415,
            )

        try:
            reader = await request.multipart()
        except Exception:
            return self._error(
                "multipart",
                "invalid multipart request",
                status=400,
            )

        source_type = "upload"

        file_data: bytes | None = None
        filename = "attachment"
        declared_mime_type = ""

        try:
            while True:
                part = await reader.next()

                if part is None:
                    break

                if part.name == "source_type":
                    source_type = (await part.text()).strip() or "upload"
                    continue

                if part.name != "file":
                    # Explicitly consume unused multipart fields.
                    await part.release()
                    continue

                if file_data is not None:
                    return self._error(
                        "file",
                        "exactly one file field is supported",
                        status=400,
                    )

                filename = part.filename or "attachment"
                declared_mime_type = (
                    part.headers.get("Content-Type", "")
                    if part.headers
                    else ""
                )

                # Important:
                # aiohttp drains an unread multipart part when reader.next()
                # advances to the next part, so the file must be read here.
                file_data = await self._read_multipart_file(part)

        except AttachmentTooLargeError as exc:
            return self._error(
                "file",
                str(exc),
                status=413,
            )
        except Exception as exc:
            return self._error(
                "multipart",
                str(exc),
                status=400,
            )

        if file_data is None:
            return self._error(
                "file",
                "multipart field 'file' is required",
                status=400,
            )

        try:
            attachment = await asyncio.to_thread(
                self.service.upload_bytes,
                file_data,
                original_filename=filename,
                declared_mime_type=declared_mime_type,
                source_type=source_type,
            )
        except AttachmentTooLargeError as exc:
            return self._error(
                "file",
                str(exc),
                status=413,
            )
        except (ValueError, AttachmentServiceError) as exc:
            return self._error(
                "file",
                str(exc),
                status=400,
            )

        return web.json_response(
            {"attachment": attachment_to_dict(attachment)},
            status=201,
        )

    async def list(self, request: web.Request) -> web.Response:
        include_deleted = (
            request.query.get("include_deleted", "")
            .strip()
            .lower()
            in {"1", "true", "yes"}
        )

        attachments = await asyncio.to_thread(
            self.service.list,
            include_deleted=include_deleted,
        )

        return web.json_response(
            {
                "attachments": [
                    attachment_to_dict(item)
                    for item in attachments
                ]
            }
        )

    async def get(self, request: web.Request) -> web.Response:
        attachment_id = request.match_info["attachment_id"]

        try:
            attachment = await asyncio.to_thread(
                self.service.get,
                attachment_id,
            )
        except AttachmentNotFoundError:
            return self._not_found(attachment_id)

        return web.json_response(
            {"attachment": attachment_to_dict(attachment)}
        )

    async def content(self, request: web.Request) -> web.StreamResponse:
        attachment_id = request.match_info["attachment_id"]

        try:
            attachment = await asyncio.to_thread(
                self.service.get,
                attachment_id,
            )

            if attachment.status.value == "deleted":
                raise AttachmentServiceError(
                    f"attachment {attachment_id!r} is deleted"
                )

            path = self.service.storage.object_path(
                attachment.object_key
            )

            if not path.is_file():
                raise AttachmentServiceError(
                    "stored attachment object is missing"
                )

        except AttachmentNotFoundError:
            return self._not_found(attachment_id)
        except AttachmentServiceError as exc:
            return self._error(
                "attachment",
                str(exc),
                status=410,
            )

        response = web.FileResponse(path)

        response.headers["Content-Type"] = (
            attachment.inferred_mime_type
            or attachment.declared_mime_type
            or "application/octet-stream"
        )

        # Do not expose the original filename directly in Content-Disposition
        # during Phase 1. The metadata API remains the source of display names.
        response.headers["Content-Disposition"] = (
            'attachment; filename="attachment"'
        )

        response.headers["X-HoneyOS-Attachment-Id"] = attachment.id
        response.headers["X-Content-Type-Options"] = "nosniff"

        return response

    async def delete(self, request: web.Request) -> web.Response:
        attachment_id = request.match_info["attachment_id"]

        try:
            attachment = await asyncio.to_thread(
                self.service.soft_delete,
                attachment_id,
            )
        except AttachmentNotFoundError:
            return self._not_found(attachment_id)

        return web.json_response(
            {"attachment": attachment_to_dict(attachment)}
        )

    async def restore(self, request: web.Request) -> web.Response:
        attachment_id = request.match_info["attachment_id"]

        try:
            attachment = await asyncio.to_thread(
                self.service.restore,
                attachment_id,
            )
        except AttachmentNotFoundError:
            return self._not_found(attachment_id)
        except AttachmentServiceError as exc:
            return self._error(
                "attachment",
                str(exc),
                status=409,
            )

        return web.json_response(
            {"attachment": attachment_to_dict(attachment)}
        )

    async def _read_multipart_file(self, part: Any) -> bytes:
        """Read exactly one multipart file with a hard bounded size.

        The file part must be consumed before advancing MultipartReader.
        """

        max_bytes = self.service.max_attachment_bytes

        chunks: list[bytes] = []
        total = 0

        while True:
            chunk = await part.read_chunk()

            if not chunk:
                break

            total += len(chunk)

            if total > max_bytes:
                raise AttachmentTooLargeError(
                    f"attachment exceeds maximum size of {max_bytes} bytes"
                )

            chunks.append(bytes(chunk))

        return b"".join(chunks)

    @staticmethod
    def _not_found(attachment_id: str) -> web.Response:
        return AttachmentHTTPHandlers._error(
            "attachment_id",
            f"attachment {attachment_id!r} was not found",
            status=404,
        )

    @staticmethod
    def _error(
        field: str,
        message: str,
        *,
        status: int,
    ) -> web.Response:
        return web.json_response(
            {
                "error": {
                    "field": field,
                    "message": message,
                }
            },
            status=status,
        )
