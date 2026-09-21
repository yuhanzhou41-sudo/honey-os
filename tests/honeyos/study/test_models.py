from datetime import date

import pytest
from pydantic import ValidationError

from honeyos.study.models import StudyPlan, StudyTask


def test_study_plan_accepts_valid_task():
    plan = StudyPlan(
        title="Example",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 22),
        tasks=[
            StudyTask(
                title="Task",
                scheduled_date=date(2026, 9, 21),
                planned_minutes=40,
            )
        ],
    )

    assert plan.schema_version == 1
    assert len(plan.tasks) == 1
    assert plan.tasks[0].plan_id == plan.id


def test_end_date_cannot_precede_start_date():
    with pytest.raises(ValidationError):
        StudyPlan(
            title="Invalid",
            start_date=date(2026, 9, 23),
            end_date=date(2026, 9, 21),
        )


def test_task_must_fall_within_plan_dates():
    with pytest.raises(ValidationError):
        StudyPlan(
            title="Invalid",
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 22),
            tasks=[
                StudyTask(
                    title="Outside",
                    scheduled_date=date(2026, 9, 23),
                )
            ],
        )


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        StudyPlan(
            title="Example",
            start_date=date(2026, 9, 21),
            end_date=date(2026, 9, 21),
            unexpected_field=True,
        )
