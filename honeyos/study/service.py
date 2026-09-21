from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import StudyPlan, StudyPlanSource, StudyTask
from .repository import StudyPlanNotFoundError, StudyRepository
from .validation import validate_study_plan


class StudyTaskNotFoundError(KeyError):
    pass


class StudyService:
    """Application layer for the frozen StudyPlan v1 domain.

    Phase 2 deliberately implements plan/task operations by loading the
    canonical aggregate, validating it, and saving it through StudyRepository.
    It does not introduce a second Study schema or write companion/study.db.
    """

    _PLAN_MUTABLE_FIELDS = {
        "title",
        "description",
        "start_date",
        "end_date",
        "status",
        "focus_minutes",
        "break_minutes",
        "long_break_minutes",
        "long_break_after_sessions",
        "goals",
    }
    _TASK_MUTABLE_FIELDS = {
        "title",
        "description",
        "scheduled_date",
        "planned_minutes",
        "status",
        "order_index",
        "review_required",
    }

    def __init__(self, repository: StudyRepository | None = None):
        self.repository = repository or StudyRepository()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def list_plans(self) -> list[StudyPlan]:
        return self.repository.list_plans()

    def get_plan(self, plan_id: str) -> StudyPlan:
        return self.repository.get_plan(plan_id)

    def create_plan(self, payload: dict[str, Any]) -> StudyPlan:
        raw = dict(payload)
        # HTTP/manual CRUD is a manual source. Do not allow clients to forge
        # import/generated provenance through this surface.
        raw.pop("id", None)
        raw.pop("schema_version", None)
        raw.pop("created_at", None)
        raw.pop("updated_at", None)
        raw["source_type"] = StudyPlanSource.MANUAL.value
        raw["tasks"] = []
        plan = validate_study_plan(raw)
        return self.repository.save_plan(plan)

    def update_plan(self, plan_id: str, patch: dict[str, Any]) -> StudyPlan:
        plan = self.repository.get_plan(plan_id)
        unknown = set(patch) - self._PLAN_MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"unsupported plan fields: {', '.join(sorted(unknown))}")

        raw = plan.model_dump()
        raw.update(patch)
        raw["updated_at"] = self._now()
        updated = validate_study_plan(raw)
        return self.repository.save_plan(updated)

    def delete_plan(self, plan_id: str) -> None:
        self.repository.delete_plan(plan_id)

    def create_task(self, plan_id: str, payload: dict[str, Any]) -> StudyPlan:
        plan = self.repository.get_plan(plan_id)
        unknown = set(payload) - self._TASK_MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"unsupported task fields: {', '.join(sorted(unknown))}")

        raw = dict(payload)
        raw.pop("status", None)  # new tasks always start planned
        raw["plan_id"] = plan.id
        if "order_index" not in raw:
            raw["order_index"] = max(
                (task.order_index for task in plan.tasks), default=0
            ) + 1
        task = StudyTask.model_validate(raw)
        plan.tasks.append(task)
        plan.updated_at = self._now()
        return self.repository.save_plan(validate_study_plan(plan))

    def update_task(
        self, plan_id: str, task_id: str, patch: dict[str, Any]
    ) -> StudyPlan:
        plan = self.repository.get_plan(plan_id)
        unknown = set(patch) - self._TASK_MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"unsupported task fields: {', '.join(sorted(unknown))}")

        for index, task in enumerate(plan.tasks):
            if task.id != task_id:
                continue
            raw = task.model_dump()
            raw.update(patch)
            raw["plan_id"] = plan.id
            raw["updated_at"] = self._now()
            plan.tasks[index] = StudyTask.model_validate(raw)
            plan.updated_at = self._now()
            return self.repository.save_plan(validate_study_plan(plan))

        raise StudyTaskNotFoundError(task_id)

    def set_task_status(
        self, plan_id: str, task_id: str, status: str
    ) -> StudyPlan:
        return self.update_task(plan_id, task_id, {"status": status})

    def delete_task(self, plan_id: str, task_id: str) -> StudyPlan:
        plan = self.repository.get_plan(plan_id)
        remaining = [task for task in plan.tasks if task.id != task_id]
        if len(remaining) == len(plan.tasks):
            raise StudyTaskNotFoundError(task_id)

        plan.tasks = remaining
        plan.updated_at = self._now()
        return self.repository.save_plan(validate_study_plan(plan))
