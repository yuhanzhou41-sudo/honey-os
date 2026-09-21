from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StudyPlanStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class StudyPlanSource(str, Enum):
    HONEYOS_GENERATED = "honeyos_generated"
    MARKDOWN_IMPORT = "markdown_import"
    MANUAL = "manual"


class StudyTaskStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    DEFERRED = "deferred"


class StudySessionType(str, Enum):
    FOCUS = "focus"
    REVIEW = "review"
    QUIZ = "quiz"
    FLASHCARD = "flashcard"


class StudySessionStatus(str, Enum):
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class StudyTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_id("task"))
    plan_id: str | None = None

    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=5000)

    scheduled_date: date
    planned_minutes: int = Field(default=40, ge=1, le=1440)

    status: StudyTaskStatus = StudyTaskStatus.PLANNED
    order_index: int = Field(default=0, ge=0)
    review_required: bool = False

    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class StudyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_id("plan"))
    schema_version: int = Field(default=1)

    title: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=10000)

    start_date: date
    end_date: date

    status: StudyPlanStatus = StudyPlanStatus.DRAFT

    focus_minutes: int = Field(default=40, ge=1, le=240)
    break_minutes: int = Field(default=10, ge=1, le=120)
    long_break_minutes: int = Field(default=25, ge=1, le=240)
    long_break_after_sessions: int = Field(default=3, ge=1, le=20)

    source_type: StudyPlanSource = StudyPlanSource.MANUAL

    goals: list[str] = Field(default_factory=list)
    tasks: list[StudyTask] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_plan(self) -> "StudyPlan":
        if self.schema_version != 1:
            raise ValueError(
                f"unsupported study plan schema_version: {self.schema_version}"
            )

        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")

        seen_ids: set[str] = set()

        for index, task in enumerate(self.tasks):
            if task.id in seen_ids:
                raise ValueError(f"duplicate task id: {task.id}")
            seen_ids.add(task.id)

            if not self.start_date <= task.scheduled_date <= self.end_date:
                raise ValueError(
                    f"task {task.id!r} scheduled_date "
                    f"{task.scheduled_date.isoformat()} is outside plan date range"
                )

            task.plan_id = self.id

            if task.order_index == 0:
                task.order_index = index + 1

        return self


class StudySession(BaseModel):
    """Frozen Phase-0 schema.

    Runtime session behaviour is implemented in a later phase.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_id("session"))
    task_id: str

    session_type: StudySessionType = StudySessionType.FOCUS
    status: StudySessionStatus = StudySessionStatus.PLANNED

    started_at: datetime | None = None
    expected_end_at: datetime | None = None
    ended_at: datetime | None = None

    planned_minutes: int = Field(default=40, ge=1, le=1440)
    actual_minutes: int = Field(default=0, ge=0, le=1440)

    user_summary: str = Field(default="", max_length=20000)

    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class StudyResource(BaseModel):
    """Frozen Phase-0 schema.

    Attachment extraction and library indexing are implemented later.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: _new_id("resource"))
    attachment_id: str

    title: str = Field(min_length=1, max_length=500)
    resource_type: str = Field(min_length=1, max_length=100)
    course_or_subject: str = Field(default="", max_length=500)

    metadata: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
