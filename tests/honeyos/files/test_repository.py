from datetime import datetime, timezone

import pytest

from honeyos.files.models import (
    Attachment,
    AttachmentSourceType,
    AttachmentStatus,
)
from honeyos.files.repository import (
    AttachmentNotFoundError,
    AttachmentRepository,
)
from honeyos.files.storage import canonical_object_key


def make_attachment(
    attachment_id: str,
    *,
    payload_sha: str = "a" * 64,
    filename: str = "notes.pdf",
) -> Attachment:
    return Attachment(
        id=attachment_id,
        original_filename=filename,
        object_key=canonical_object_key(payload_sha),
        declared_mime_type="application/pdf",
        inferred_mime_type="application/pdf",
        size_bytes=123,
        sha256=payload_sha,
        source_type=AttachmentSourceType.UPLOAD,
        status=AttachmentStatus.READY,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_initialize_creates_database(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    repo.initialize()

    assert repo.db_path.is_file()


def test_save_and_get_attachment(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")
    attachment = make_attachment("att_one")

    saved = repo.save(attachment)
    loaded = repo.get("att_one")

    assert saved.id == "att_one"
    assert loaded.id == "att_one"
    assert loaded.object_key == attachment.object_key
    assert loaded.sha256 == attachment.sha256


def test_save_updates_existing_attachment(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    attachment = make_attachment("att_one", filename="first.pdf")
    repo.save(attachment)

    updated = attachment.model_copy(
        update={"original_filename": "renamed.pdf"}
    )
    repo.save(updated)

    loaded = repo.get("att_one")

    assert loaded.original_filename == "renamed.pdf"


def test_get_missing_attachment_raises(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    with pytest.raises(AttachmentNotFoundError):
        repo.get("missing")


def test_list_excludes_soft_deleted_by_default(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    repo.save(make_attachment("att_one"))
    repo.save(make_attachment("att_two"))

    repo.soft_delete("att_two")

    visible = repo.list()
    all_items = repo.list(include_deleted=True)

    assert [item.id for item in visible] == ["att_one"]
    assert {item.id for item in all_items} == {"att_one", "att_two"}


def test_soft_delete_marks_deleted(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    repo.save(make_attachment("att_one"))

    deleted = repo.soft_delete("att_one")

    assert deleted.status == AttachmentStatus.DELETED
    assert repo.get("att_one").status == AttachmentStatus.DELETED


def test_restore_soft_deleted_attachment(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    repo.save(make_attachment("att_one"))
    repo.soft_delete("att_one")

    restored = repo.restore("att_one")

    assert restored.status == AttachmentStatus.READY


def test_hard_delete_removes_metadata(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    repo.save(make_attachment("att_one"))

    deleted = repo.hard_delete("att_one")

    assert deleted.id == "att_one"

    with pytest.raises(AttachmentNotFoundError):
        repo.get("att_one")


def test_multiple_metadata_rows_can_share_object(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    shared_sha = "b" * 64

    repo.save(make_attachment("att_one", payload_sha=shared_sha))
    repo.save(make_attachment("att_two", payload_sha=shared_sha))

    first = repo.get("att_one")
    second = repo.get("att_two")

    assert first.object_key == second.object_key
    assert repo.count_object_references(first.object_key) == 2


def test_soft_deleted_attachment_is_not_live_reference(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    shared_sha = "c" * 64

    first = repo.save(make_attachment("att_one", payload_sha=shared_sha))
    repo.save(make_attachment("att_two", payload_sha=shared_sha))

    repo.soft_delete("att_one")

    assert repo.count_object_references(first.object_key) == 1
    assert repo.count_object_references(
        first.object_key,
        include_deleted=True,
    ) == 2


def test_last_live_reference_detection(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    attachment = repo.save(make_attachment("att_one"))

    assert repo.has_live_object_reference(attachment.object_key) is True

    repo.soft_delete("att_one")

    assert repo.has_live_object_reference(attachment.object_key) is False


def test_find_by_sha256(tmp_path):
    repo = AttachmentRepository(tmp_path / "attachments")

    target_sha = "d" * 64

    repo.save(make_attachment("att_one", payload_sha=target_sha))
    repo.save(make_attachment("att_two", payload_sha=target_sha))
    repo.save(make_attachment("att_three", payload_sha="e" * 64))

    found = repo.find_by_sha256(target_sha)

    assert [item.id for item in found] == ["att_one", "att_two"]
