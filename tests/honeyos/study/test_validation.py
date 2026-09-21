from datetime import date

import pytest

from honeyos.study.models import StudyPlan
from honeyos.study.validation import (
    StudyPlanValidationError,
    validate_study_plan,
)


def test_generated_plan_uses_same_validation_gate():
    generated = {
        "schema_version": 1,
        "title": "HoneyOS Generated Plan",
        "start_date": "2026-09-21",
        "end_date": "2026-09-21",
        "source_type": "honeyos_generated",
        "tasks": [
            {
                "title": "Generated task",
                "scheduled_date": "2026-09-21",
                "planned_minutes": 40,
            }
        ],
    }

    plan = validate_study_plan(generated)

    assert isinstance(plan, StudyPlan)
    assert plan.tasks[0].plan_id == plan.id


def test_invalid_generated_plan_uses_same_validation_gate():
    with pytest.raises(StudyPlanValidationError):
        validate_study_plan(
            {
                "schema_version": 1,
                "title": "Broken",
                "start_date": "2026-09-23",
                "end_date": "2026-09-21",
            }
        )


def test_schema_version_other_than_one_is_rejected():
    with pytest.raises(StudyPlanValidationError):
        validate_study_plan(
            {
                "schema_version": 2,
                "title": "Future",
                "start_date": date(2026, 9, 21),
                "end_date": date(2026, 9, 21),
            }
        )
