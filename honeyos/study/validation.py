from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from .models import StudyPlan


class StudyPlanValidationError(ValueError):
    """Raised when external or generated StudyPlan data is invalid."""


def validate_study_plan(value: StudyPlan | dict[str, Any]) -> StudyPlan:
    """Validate all StudyPlan inputs through one canonical gate.

    HoneyOS-generated plans and imported Markdown plans must both pass here.
    """

    try:
        if isinstance(value, StudyPlan):
            # Re-validate from serialized data rather than trusting an already
            # constructed object. This keeps all input channels equivalent.
            return StudyPlan.model_validate(value.model_dump())
        return StudyPlan.model_validate(value)
    except ValidationError as exc:
        raise StudyPlanValidationError(str(exc)) from exc
    except ValueError as exc:
        raise StudyPlanValidationError(str(exc)) from exc


def semantic_plan_dict(plan: StudyPlan) -> dict[str, Any]:
    """Return fields relevant to Markdown semantic round-trip tests.

    Runtime timestamps are deliberately excluded from interchange equality.
    """

    return {
        "schema_version": plan.schema_version,
        "title": plan.title,
        "description": plan.description,
        "start_date": plan.start_date.isoformat(),
        "end_date": plan.end_date.isoformat(),
        "status": plan.status.value,
        "focus_minutes": plan.focus_minutes,
        "break_minutes": plan.break_minutes,
        "long_break_minutes": plan.long_break_minutes,
        "long_break_after_sessions": plan.long_break_after_sessions,
        "source_type": plan.source_type.value,
        "goals": list(plan.goals),
        "tasks": [
            {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "scheduled_date": task.scheduled_date.isoformat(),
                "planned_minutes": task.planned_minutes,
                "status": task.status.value,
                "order_index": task.order_index,
                "review_required": task.review_required,
            }
            for task in plan.tasks
        ],
    }
