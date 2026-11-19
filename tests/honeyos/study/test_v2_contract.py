from datetime import date
import sqlite3

import pytest

from honeyos.study.markdown import (
    StudyPlanMarkdownError, export_study_plan_markdown, parse_study_plan_markdown,
)
from honeyos.study.models import StudyPlan
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService
from honeyos.study.validation import semantic_plan_dict


def v2_payload():
    return {
        "schema_version": 2, "title": "Two-day revision",
        "start_date": "2026-11-19", "end_date": "2026-11-20",
        "tasks": [{
            "title": "Essential recall", "scheduled_date": "2026-11-19",
            "priority": "must", "minimum_required": True, "kind": "flashcard",
            "planned_minutes": 15,
        }],
        "flex_slots": [{"scheduled_date": "2026-11-20", "planned_minutes": 30}],
    }


def test_v2_markdown_and_repository_roundtrip(tmp_path):
    plan = StudyPlan.model_validate(v2_payload())
    markdown = export_study_plan_markdown(plan)
    parsed = parse_study_plan_markdown(markdown)
    assert semantic_plan_dict(parsed) == semantic_plan_dict(plan)
    repo = StudyRepository(tmp_path)
    saved = repo.save_new_plan(parsed)
    restored = StudyRepository(tmp_path).get_plan(saved.id)
    assert semantic_plan_dict(restored) == semantic_plan_dict(plan)
    assert len(restored.tasks) == 1
    assert restored.flex_slots[0].scheduled_date == date(2026, 11, 20)


@pytest.mark.parametrize("changes", [
    {"priority": "optional"}, {"kind": "unknown"}, {"priority": "unknown"},
])
def test_invalid_v2_task_rejected(changes):
    payload = v2_payload()
    payload["tasks"][0].update(changes)
    with pytest.raises(ValueError):
        StudyPlan.model_validate(payload)


def test_v2_fields_cannot_be_silently_exported_as_v1():
    payload = v2_payload()
    payload["schema_version"] = 1
    with pytest.raises(ValueError, match="V2 fields"):
        StudyPlan.model_validate(payload)


@pytest.mark.parametrize("slot", [
    {"scheduled_date": "2026-11-21", "planned_minutes": 30},
    {"scheduled_date": "2026-11-20", "planned_minutes": 0},
    {"scheduled_date": "2026-11-20", "planned_minutes": 30, "sunlight": 9},
])
def test_invalid_flex_slots_rejected(slot):
    payload = v2_payload()
    payload["flex_slots"] = [slot]
    with pytest.raises(ValueError):
        StudyPlan.model_validate(payload)


def test_v2_unknown_frontmatter_and_v1_metadata_rejected():
    raw = export_study_plan_markdown(StudyPlan.model_validate(v2_payload()))
    with pytest.raises(StudyPlanMarkdownError):
        parse_study_plan_markdown(raw.replace("study_plan_version: 2", "study_plan_version: 2\nsunlight: 8"))
    with pytest.raises(StudyPlanMarkdownError):
        parse_study_plan_markdown(raw.replace("study_plan_version: 2", "study_plan_version: 1"))


def test_upgrade_legacy_database_and_restore_backup(tmp_path):
    repo = StudyRepository(tmp_path)
    service = StudyService(repo)
    old = service.create_plan({
        "title": "Legacy", "start_date": "2026-11-19", "end_date": "2026-11-20",
    })
    old = service.create_task(old.id, {"title": "Finished", "scheduled_date": "2026-11-19"})
    session = service.create_session(old.id, old.tasks[0].id, {"planned_minutes": 25})
    old = service.set_task_status(old.id, old.tasks[0].id, "completed")
    with sqlite3.connect(repo.db_path) as db:
        db.execute("DROP TABLE study_plan_definitions")
        db.commit()
        with sqlite3.connect(tmp_path / "backup.db") as backup:
            db.backup(backup)
    upgraded = StudyRepository(tmp_path)
    loaded = upgraded.get_plan(old.id)
    assert loaded.schema_version == 1 and loaded.tasks[0].status.value == "completed"
    assert loaded.flex_slots == []
    upgraded.save_new_plan(StudyPlan.model_validate(v2_payload()))
    assert StudyService(upgraded).get_session(session.id).task_id == old.tasks[0].id
    with sqlite3.connect(tmp_path / "backup.db") as backup:
        with sqlite3.connect(repo.db_path) as db:
            backup.backup(db)
    restored = StudyRepository(tmp_path)
    assert [p.id for p in restored.list_plans()] == [old.id]
    assert StudyService(restored).get_session(session.id).task_id == old.tasks[0].id



def test_v2_service_preview_import_and_task_edit(tmp_path):
    service = StudyService(StudyRepository(tmp_path))
    raw = export_study_plan_markdown(StudyPlan.model_validate(v2_payload()))
    preview = service.preview_markdown_plan(raw)
    assert preview.schema_version == 2
    assert service.list_plans() == []
    saved = service.import_markdown_plan(raw)
    changed = service.update_task(saved.id, saved.tasks[0].id, {"kind": "quiz"})
    assert changed.tasks[0].kind == "quiz"
    assert changed.flex_slots == saved.flex_slots
    with pytest.raises(ValueError):
        service.update_task(saved.id, saved.tasks[0].id, {"priority": "optional"})
    assert service.get_plan(saved.id).tasks[0].priority == "must"


def test_v2_import_does_not_create_completion_facts(tmp_path):
    service = StudyService(StudyRepository(tmp_path))
    raw = export_study_plan_markdown(StudyPlan.model_validate(v2_payload()))
    raw = raw.replace("- [ ]", "- [x]").replace("status: planned", "status: completed")
    saved = service.import_markdown_plan(raw)
    assert saved.tasks[0].status.value == "planned"
