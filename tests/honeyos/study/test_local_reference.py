from concurrent.futures import ThreadPoolExecutor
import os

import pytest

from honeyos.study import StudyRepository, StudyService
from honeyos.study.storage import StudyStorageError, StudyStorageManager


def test_cross_drive_references_reuse_one_record_and_no_attachment(tmp_path):
    mounts = tmp_path / "mnt"
    left = mounts / "c" / "文档"
    right = mounts / "e"
    left.mkdir(parents=True)
    right.mkdir()
    first, second = left / "讲义.txt", right / "副本.txt"
    text = "冰岛项目的开课口令是 Starling-457。"
    first.write_text(text, encoding="utf-8")
    second.write_text(text, encoding="utf-8")
    study = StudyService(StudyRepository(tmp_path / "home"), local_mount_root=mounts)

    def reference(path):
        return study.reference_local_file(path)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reference, [r"C:\文档\讲义.txt", r"E:\副本.txt"]))

    assert len(study.list_resources()) == 1
    assert sum(not reused for _, reused in results) == 1
    resource = results[0][0]
    assert results[1][0].id == resource.id
    assert resource.attachment_id == ""
    assert not study.attachments.repository.find_by_sha256(resource.metadata["local_source"]["sha256"])
    assert len(study.search_resources(query="Starling")) == 1
    assert text in study.build_chat_resource_context([resource.id])
    assert str(mounts) not in study.build_chat_resource_context([resource.id])
    original = study.describe_resource_storage(resource)
    assert original["original_bytes"] == len(text.encode())

    from pathlib import Path
    saved = Path(original["source_path"])
    alternative = second if saved == first else first
    saved.rename(saved.with_suffix(".moved"))
    assert study.describe_resource_storage(resource)["source_status"] == "offline"
    with pytest.raises(ValueError, match="暂不可访问"):
        study.build_chat_resource_context([resource.id])

    wrong = alternative.with_name("wrong.txt")
    wrong.write_text("different", encoding="utf-8")
    with pytest.raises(ValueError, match="内容一致"):
        study.reference_local_file(str(wrong), resource_id=resource.id)
    recovered, reused = study.reference_local_file(str(alternative), resource_id=resource.id)
    assert reused and recovered.id == resource.id
    assert study.describe_resource_storage(recovered)["source_status"] == "online"

    study.delete_resource(resource.id)
    assert alternative.read_text(encoding="utf-8") == text
    assert study.search_resources(query="Starling") == []


def test_existing_managed_resource_and_failed_import(tmp_path):
    mounts = tmp_path / "mnt"
    drive = mounts / "d"
    drive.mkdir(parents=True)
    file = drive / "notes.txt"
    file.write_text("existing study copy", encoding="utf-8")
    study = StudyService(StudyRepository(tmp_path / "home"), local_mount_root=mounts)
    attachment = study.attachments.upload_bytes(
        file.read_bytes(), original_filename=file.name, source_type="study"
    )
    existing = study.create_resource({"attachment_id": attachment.id})
    resource, reused = study.reference_local_file(str(file))
    assert reused and resource.id == existing.id
    assert study.describe_resource_storage(resource)["has_managed_attachment"]
    assert study.attachments.read_bytes(attachment.id) == file.read_bytes()

    invalid = drive / "invalid.txt"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        study.reference_local_file(str(invalid))
    invalid.write_text("corrected", encoding="utf-8")
    corrected, reused = study.reference_local_file(str(invalid))
    assert not reused
    assert study.get_resource_content(corrected.id)["extracted_text"] == "corrected"
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    (drive / "outside.txt").symlink_to(outside)
    with pytest.raises(ValueError):
        study.reference_local_file(str(drive / "outside.txt"))


def test_expired_cleanup_keeps_recent_symlink_and_referenced_original(tmp_path):
    manager = StudyStorageManager(tmp_path / "registry", tmp_path / "library", tmp_path / "mnt")
    library = manager.create_library(tmp_path / "library", "Study", mode="default")
    temporary = tmp_path / "library" / "temp"
    expired, recent, protected = (temporary / name for name in ("expired", "recent", "protected"))
    for path in (expired, recent, protected):
        path.write_bytes(b"test")
    target = tmp_path / "original"
    target.write_bytes(b"keep")
    (temporary / "link").symlink_to(target)
    os.utime(expired, (1, 1))
    os.utime(protected, (1, 1))
    # Windows lets the same file be selected with different casing.
    protected_names = {protected.with_name(protected.name.upper())}
    result = manager.cleanup(library["library_id"], "expired_temp", protected_paths=protected_names)
    assert result["freed_bytes"] == 4
    assert not expired.exists()
    assert recent.exists() and protected.exists() and target.exists()
    assert (temporary / "link").is_symlink()
    with pytest.raises(StudyStorageError, match="原文件"):
        manager.cleanup(library["library_id"], "temp", protected_paths=protected_names)
