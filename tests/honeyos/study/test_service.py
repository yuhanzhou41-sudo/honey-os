from datetime import date

import pytest

from honeyos.study.models import StudyTaskStatus
from honeyos.study.repository import StudyPlanNotFoundError, StudyRepository
from honeyos.study.service import StudyService, StudyTaskNotFoundError


def plan_payload():
    return {
        "title": "Phase 2 plan",
        "description": "canonical",
        "start_date": "2026-09-21",
        "end_date": "2026-09-23",
        "goals": ["finish review"],
    }


def test_service_plan_crud_uses_canonical_database(tmp_path):
    service = StudyService(StudyRepository(tmp_path))
    plan = service.create_plan(plan_payload())

    assert service.get_plan(plan.id).title == "Phase 2 plan"
    assert [p.id for p in service.list_plans()] == [plan.id]
    assert (tmp_path / "study" / "study.db").exists()
    assert not (tmp_path / "companion" / "study.db").exists()

    updated = service.update_plan(plan.id, {"title": "Updated"})
    assert updated.title == "Updated"

    service.delete_plan(plan.id)
    with pytest.raises(StudyPlanNotFoundError):
        service.get_plan(plan.id)


def test_service_task_crud_and_status(tmp_path):
    service = StudyService(StudyRepository(tmp_path))
    plan = service.create_plan(plan_payload())

    plan = service.create_task(
        plan.id,
        {
            "title": "Recall",
            "description": "closed-book",
            "scheduled_date": "2026-09-22",
            "planned_minutes": 30,
            "review_required": True,
        },
    )
    task = plan.tasks[0]
    assert task.plan_id == plan.id
    assert task.status is StudyTaskStatus.PLANNED

    plan = service.update_task(
        plan.id, task.id, {"title": "Recall again", "planned_minutes": 35}
    )
    assert plan.tasks[0].title == "Recall again"
    assert plan.tasks[0].planned_minutes == 35

    plan = service.set_task_status(plan.id, task.id, "completed")
    assert plan.tasks[0].status is StudyTaskStatus.COMPLETED

    plan = service.delete_task(plan.id, task.id)
    assert plan.tasks == []


def test_service_rejects_task_outside_plan_range(tmp_path):
    service = StudyService(StudyRepository(tmp_path))
    plan = service.create_plan(plan_payload())

    with pytest.raises(Exception):
        service.create_task(
            plan.id,
            {"title": "Outside", "scheduled_date": date(2026, 9, 24)},
        )


def test_service_rejects_frozen_or_unknown_fields(tmp_path):
    service = StudyService(StudyRepository(tmp_path))
    plan = service.create_plan(plan_payload())

    with pytest.raises(ValueError):
        service.update_plan(plan.id, {"schema_version": 3})

    with pytest.raises(ValueError):
        service.create_task(
            plan.id,
            {
                "title": "Task",
                "scheduled_date": "2026-09-21",
                "points": 50,
            },
        )


def test_missing_task_has_clear_error(tmp_path):
    service = StudyService(StudyRepository(tmp_path))
    plan = service.create_plan(plan_payload())

    with pytest.raises(StudyTaskNotFoundError):
        service.update_task(plan.id, "task_missing", {"status": "completed"})


def test_explicit_v2_upgrade_preserves_tasks_and_rejects_downgrade(tmp_path):
    service=StudyService(StudyRepository(tmp_path))
    plan=service.create_plan(plan_payload())
    plan=service.create_task(plan.id,{"title":"Existing","scheduled_date":plan.start_date})
    upgraded=service.update_plan(plan.id,{"schema_version":2})
    assert upgraded.schema_version==2 and upgraded.tasks[0].id==plan.tasks[0].id
    with pytest.raises(ValueError):
        service.update_plan(plan.id,{"schema_version":1})
