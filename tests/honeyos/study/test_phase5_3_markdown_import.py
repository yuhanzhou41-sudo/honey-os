import pytest

from honeyos.study.models import StudyPlanSource
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService


VALID_MARKDOWN = """---
study_plan_version: 1
title: Imported Plan
description: Phase 5.3 import
start_date: 2026-09-23
end_date: 2026-09-24
focus_minutes: 25
break_minutes: 5
long_break_minutes: 15
long_break_after_sessions: 4
---

# Goals
- 完成导入测试

# Schedule

## 2026-09-23

- [ ] 第一项任务
  duration: 30
  review: true
  description: 测试预览与确认

## 2026-09-24

- [ ] 第二项任务
  duration: 20
  review: false
"""


def make_service(tmp_path):
    return StudyService(StudyRepository(tmp_path))


def test_preview_markdown_plan_does_not_persist(tmp_path):
    service = make_service(tmp_path)

    preview = service.preview_markdown_plan(VALID_MARKDOWN)

    assert preview.title == "Imported Plan"
    assert preview.source_type is StudyPlanSource.MARKDOWN_IMPORT
    assert len(preview.tasks) == 2
    assert preview.tasks[0].review_required is True
    assert service.list_plans() == []


def test_import_markdown_plan_persists_canonical_plan_and_tasks(tmp_path):
    service = make_service(tmp_path)

    imported = service.import_markdown_plan(VALID_MARKDOWN)
    loaded = service.get_plan(imported.id)

    assert loaded.title == "Imported Plan"
    assert loaded.source_type is StudyPlanSource.MARKDOWN_IMPORT
    assert [task.title for task in loaded.tasks] == ["第一项任务", "第二项任务"]
    assert loaded.tasks[0].plan_id == loaded.id


def test_import_forces_markdown_source_type(tmp_path):
    service = make_service(tmp_path)
    text = VALID_MARKDOWN.replace(
        "focus_minutes: 25",
        "source_type: manual\nfocus_minutes: 25",
    )

    preview = service.preview_markdown_plan(text)
    imported = service.import_markdown_plan(text)

    assert preview.source_type is StudyPlanSource.MARKDOWN_IMPORT
    assert imported.source_type is StudyPlanSource.MARKDOWN_IMPORT


def test_invalid_markdown_never_persists(tmp_path):
    service = make_service(tmp_path)
    invalid = VALID_MARKDOWN.replace(
        "end_date: 2026-09-24",
        "end_date: 2026-09-22",
    )

    with pytest.raises(ValueError):
        service.preview_markdown_plan(invalid)

    with pytest.raises(ValueError):
        service.import_markdown_plan(invalid)

    assert service.list_plans() == []


def test_duplicate_explicit_plan_id_is_rejected_without_overwrite(tmp_path):
    service = make_service(tmp_path)
    text = VALID_MARKDOWN.replace(
        "title: Imported Plan",
        "id: plan_fixed_phase53\ntitle: Imported Plan",
    )

    first = service.import_markdown_plan(text)

    with pytest.raises(ValueError, match="already exists"):
        service.import_markdown_plan(text)

    loaded = service.get_plan(first.id)
    assert loaded.title == "Imported Plan"


def test_empty_markdown_is_rejected(tmp_path):
    service = make_service(tmp_path)

    with pytest.raises(ValueError):
        service.preview_markdown_plan("   ")

    with pytest.raises(ValueError):
        service.import_markdown_plan("")
