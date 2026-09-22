from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import (
    StudyPlan,
    StudyPlanSource,
    StudySession,
    StudySessionStatus,
    StudySessionType,
    StudyTask,
    StudyResource,
)
from .pomodoro import StudyPomodoroScheduler
from .library import StudyLibraryIndex
from honeyos.files.models import AttachmentStatus
from honeyos.files.service import AttachmentService
from .repository import (
    StudyPlanNotFoundError,
    StudyRepository,
    StudyResourceNotFoundError,
)
from .session_store import StudySessionNotFoundError, StudySessionStore
from .validation import validate_study_plan


class StudyTaskNotFoundError(KeyError):
    pass


class StudyService:
    """Canonical Study application layer for Phase 2 + Phase 3."""

    _PLAN_MUTABLE_FIELDS = {
        "title", "description", "start_date", "end_date", "status",
        "focus_minutes", "break_minutes", "long_break_minutes",
        "long_break_after_sessions", "goals",
    }
    _TASK_MUTABLE_FIELDS = {
        "title", "description", "scheduled_date", "planned_minutes",
        "status", "order_index", "review_required",
    }
    _SESSION_CREATE_FIELDS = {"planned_minutes", "user_summary", "session_type"}

    def __init__(
        self,
        repository: StudyRepository | None = None,
        *,
        session_store: StudySessionStore | None = None,
        pomodoro_scheduler: StudyPomodoroScheduler | None = None,
    ):
        self.repository = repository or StudyRepository()
        self.sessions = session_store or StudySessionStore(self.repository.db_path)
        self.pomodoro_scheduler = pomodoro_scheduler or StudyPomodoroScheduler()
        self.library = StudyLibraryIndex(self.repository.db_path)
        self.attachments = AttachmentService(self.repository.study_dir.parent / "files")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def list_plans(self) -> list[StudyPlan]:
        return self.repository.list_plans()

    def get_plan(self, plan_id: str) -> StudyPlan:
        return self.repository.get_plan(plan_id)

    def create_plan(self, payload: dict[str, Any]) -> StudyPlan:
        raw = dict(payload)
        raw.pop("id", None)
        raw.pop("schema_version", None)
        raw.pop("created_at", None)
        raw.pop("updated_at", None)
        raw["source_type"] = StudyPlanSource.MANUAL.value
        raw.setdefault("focus_minutes", 25)
        raw.setdefault("break_minutes", 5)
        raw.setdefault("long_break_minutes", 15)
        raw.setdefault("long_break_after_sessions", 4)
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
        return self.repository.save_plan(validate_study_plan(raw))

    def delete_plan(self, plan_id: str) -> None:
        self.repository.delete_plan(plan_id)

    def create_task(self, plan_id: str, payload: dict[str, Any]) -> StudyPlan:
        plan = self.repository.get_plan(plan_id)
        unknown = set(payload) - self._TASK_MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"unsupported task fields: {', '.join(sorted(unknown))}")
        raw = dict(payload)
        raw.pop("status", None)
        raw["plan_id"] = plan.id
        raw.setdefault("planned_minutes", plan.focus_minutes)
        if "order_index" not in raw:
            raw["order_index"] = max(
                (task.order_index for task in plan.tasks), default=0
            ) + 1
        task = StudyTask.model_validate(raw)
        plan.tasks.append(task)
        plan.updated_at = self._now()
        return self.repository.save_plan(validate_study_plan(plan))

    def update_task(self, plan_id: str, task_id: str, patch: dict[str, Any]) -> StudyPlan:
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

    def set_task_status(self, plan_id: str, task_id: str, status: str) -> StudyPlan:
        return self.update_task(plan_id, task_id, {"status": status})

    def delete_task(self, plan_id: str, task_id: str) -> StudyPlan:
        plan = self.repository.get_plan(plan_id)
        remaining = [task for task in plan.tasks if task.id != task_id]
        if len(remaining) == len(plan.tasks):
            raise StudyTaskNotFoundError(task_id)
        plan.tasks = remaining
        plan.updated_at = self._now()
        return self.repository.save_plan(validate_study_plan(plan))

    def _get_task(self, plan_id: str, task_id: str) -> tuple[StudyPlan, StudyTask]:
        plan = self.repository.get_plan(plan_id)
        for task in plan.tasks:
            if task.id == task_id:
                return plan, task
        raise StudyTaskNotFoundError(task_id)

    @staticmethod
    def _elapsed_with_running_tail(runtime, now: datetime) -> int:
        elapsed = max(0, int(runtime.elapsed_seconds))
        if runtime.last_resumed_at is not None:
            elapsed += max(0, int((now - runtime.last_resumed_at).total_seconds()))
        return elapsed

    def get_pomodoro_state(self, plan_id: str) -> dict[str, Any]:
        plan = self.repository.get_plan(plan_id)
        sessions = [
            self._reconcile_due_session(session)
            for session in self.sessions.list_plan_sessions(plan_id)
        ]

        active = next(
            (
                session
                for session in reversed(sessions)
                if session.status
                in {
                    StudySessionStatus.PLANNED,
                    StudySessionStatus.RUNNING,
                    StudySessionStatus.PAUSED,
                }
            ),
            None,
        )

        completed = [
            session
            for session in sessions
            if session.status is StudySessionStatus.COMPLETED
        ]

        focuses_in_cycle = 0
        next_type = StudySessionType.FOCUS

        for session in completed:
            if session.session_type is StudySessionType.FOCUS:
                focuses_in_cycle += 1
                if focuses_in_cycle >= plan.long_break_after_sessions:
                    next_type = StudySessionType.LONG_BREAK
                else:
                    next_type = StudySessionType.SHORT_BREAK
            elif session.session_type is StudySessionType.LONG_BREAK:
                focuses_in_cycle = 0
                next_type = StudySessionType.FOCUS
            elif session.session_type is StudySessionType.SHORT_BREAK:
                next_type = StudySessionType.FOCUS

        if active is not None:
            next_type = active.session_type

        if next_type is StudySessionType.FOCUS:
            next_minutes = plan.focus_minutes
        elif next_type is StudySessionType.LONG_BREAK:
            next_minutes = plan.long_break_minutes
        else:
            next_minutes = plan.break_minutes

        return {
            "focuses_in_cycle": focuses_in_cycle,
            "cycle_length": plan.long_break_after_sessions,
            "next_session_type": next_type.value,
            "next_minutes": next_minutes,
            "current_session_id": active.id if active else None,
            "current_session_type": active.session_type.value if active else None,
            "current_session_status": active.status.value if active else None,
        }

    def create_session(
        self, plan_id: str, task_id: str, payload: dict[str, Any]
    ) -> StudySession:
        plan, task = self._get_task(plan_id, task_id)
        unknown = set(payload) - self._SESSION_CREATE_FIELDS
        if unknown:
            raise ValueError(
                f"unsupported session fields: {', '.join(sorted(unknown))}"
            )

        state = self.get_pomodoro_state(plan_id)
        if state["current_session_id"]:
            raise ValueError("another Pomodoro session is already active for this plan")

        expected_type = StudySessionType(state["next_session_type"])
        requested_type = StudySessionType(
            payload.get("session_type") or expected_type.value
        )
        if requested_type is not expected_type:
            raise ValueError(
                f"next Pomodoro session must be {expected_type.value!r}"
            )

        if (
            requested_type is StudySessionType.FOCUS
            and task.status.value not in {"planned", "in_progress"}
        ):
            raise ValueError(
                f"cannot create focus session for task in status {task.status.value!r}"
            )

        default_minutes = {
            StudySessionType.FOCUS: plan.focus_minutes,
            StudySessionType.SHORT_BREAK: plan.break_minutes,
            StudySessionType.LONG_BREAK: plan.long_break_minutes,
        }[requested_type]

        raw = dict(payload)
        raw["task_id"] = task.id
        raw["session_type"] = requested_type.value
        raw["status"] = StudySessionStatus.PLANNED.value
        raw["planned_minutes"] = int(raw.get("planned_minutes") or default_minutes)
        raw["actual_minutes"] = 0

        session = self.sessions.save_session(StudySession.model_validate(raw))
        self.sessions.save_runtime(
            session.id,
            elapsed_seconds=0,
            remaining_seconds=session.planned_minutes * 60,
            last_resumed_at=None,
            scheduler_job_id=None,
            updated_at=session.updated_at,
        )
        return session

    def list_sessions(self, task_id: str | None = None) -> list[StudySession]:
        return [self._reconcile_due_session(s) for s in self.sessions.list_sessions(task_id)]

    def get_session(self, session_id: str) -> StudySession:
        return self._reconcile_due_session(self.sessions.get_session(session_id))

    def _reconcile_due_session(self, session: StudySession) -> StudySession:
        now = self._now()
        if (
            session.status is StudySessionStatus.RUNNING
            and session.expected_end_at is not None
            and session.expected_end_at <= now
        ):
            return self.complete_session(session.id, scheduled=True)
        return session

    def start_session(self, session_id: str) -> StudySession:
        session = self.sessions.get_session(session_id)
        if session.status is not StudySessionStatus.PLANNED:
            raise ValueError("only planned study sessions can be started")
        now = self._now()
        remaining = session.planned_minutes * 60
        expected_end = now + timedelta(seconds=remaining)
        job_id = self.pomodoro_scheduler.schedule_completion(session.id, expected_end)
        try:
            session.status = StudySessionStatus.RUNNING
            session.started_at = now
            session.expected_end_at = expected_end
            session.ended_at = None
            session.updated_at = now
            saved = self.sessions.save_session(session)
            self.sessions.save_runtime(
                session.id,
                elapsed_seconds=0,
                remaining_seconds=remaining,
                last_resumed_at=now,
                scheduler_job_id=job_id,
                updated_at=now,
            )
        except Exception:
            self.pomodoro_scheduler.cancel_completion(job_id)
            raise
        return saved

    def pause_session(self, session_id: str) -> StudySession:
        session = self.sessions.get_session(session_id)
        if session.status is not StudySessionStatus.RUNNING:
            raise ValueError("only running study sessions can be paused")
        now = self._now()
        runtime = self.sessions.get_runtime(session.id)
        elapsed = min(
            session.planned_minutes * 60,
            self._elapsed_with_running_tail(runtime, now),
        )
        remaining = max(0, session.planned_minutes * 60 - elapsed)
        if remaining <= 0:
            return self.complete_session(session.id, scheduled=True)
        session.status = StudySessionStatus.PAUSED
        session.expected_end_at = None
        session.actual_minutes = min(session.planned_minutes, elapsed // 60)
        session.updated_at = now
        saved = self.sessions.save_session(session)
        self.sessions.save_runtime(
            session.id,
            elapsed_seconds=elapsed,
            remaining_seconds=remaining,
            last_resumed_at=None,
            scheduler_job_id=None,
            updated_at=now,
        )
        self.pomodoro_scheduler.cancel_completion(runtime.scheduler_job_id)
        return saved

    def resume_session(self, session_id: str) -> StudySession:
        session = self.sessions.get_session(session_id)
        if session.status is not StudySessionStatus.PAUSED:
            raise ValueError("only paused study sessions can be resumed")
        now = self._now()
        runtime = self.sessions.get_runtime(session.id)
        remaining = max(0, int(runtime.remaining_seconds))
        if remaining <= 0:
            return self.complete_session(session.id, scheduled=True)
        expected_end = now + timedelta(seconds=remaining)
        job_id = self.pomodoro_scheduler.schedule_completion(session.id, expected_end)
        try:
            session.status = StudySessionStatus.RUNNING
            session.expected_end_at = expected_end
            session.updated_at = now
            saved = self.sessions.save_session(session)
            self.sessions.save_runtime(
                session.id,
                elapsed_seconds=runtime.elapsed_seconds,
                remaining_seconds=remaining,
                last_resumed_at=now,
                scheduler_job_id=job_id,
                updated_at=now,
            )
        except Exception:
            self.pomodoro_scheduler.cancel_completion(job_id)
            raise
        return saved

    def complete_session(self, session_id: str, *, scheduled: bool = False) -> StudySession:
        session = self.sessions.get_session(session_id)
        if session.status in {StudySessionStatus.COMPLETED, StudySessionStatus.ABANDONED}:
            return session
        if scheduled and session.status is not StudySessionStatus.RUNNING:
            return session
        now = self._now()
        if scheduled and session.expected_end_at is not None and now < session.expected_end_at:
            return session
        runtime = self.sessions.get_runtime(session.id)
        if scheduled:
            elapsed = session.planned_minutes * 60
            ended_at = session.expected_end_at or now
            actual_minutes = session.planned_minutes
        else:
            elapsed = min(
                session.planned_minutes * 60,
                self._elapsed_with_running_tail(runtime, now),
            )
            ended_at = now
            actual_minutes = min(session.planned_minutes, elapsed // 60)
        session.status = StudySessionStatus.COMPLETED
        session.ended_at = ended_at
        session.actual_minutes = actual_minutes
        session.updated_at = now
        saved = self.sessions.save_session(session)
        self.sessions.save_runtime(
            session.id,
            elapsed_seconds=elapsed,
            remaining_seconds=max(0, session.planned_minutes * 60 - elapsed),
            last_resumed_at=None,
            scheduler_job_id=None,
            updated_at=now,
        )
        if not scheduled:
            self.pomodoro_scheduler.cancel_completion(runtime.scheduler_job_id)
        return saved

    def abandon_session(self, session_id: str) -> StudySession:
        session = self.sessions.get_session(session_id)
        if session.status in {StudySessionStatus.COMPLETED, StudySessionStatus.ABANDONED}:
            return session
        now = self._now()
        runtime = self.sessions.get_runtime(session.id)
        elapsed = min(
            session.planned_minutes * 60,
            self._elapsed_with_running_tail(runtime, now),
        )
        session.status = StudySessionStatus.ABANDONED
        session.ended_at = now
        session.expected_end_at = None
        session.actual_minutes = min(session.planned_minutes, elapsed // 60)
        session.updated_at = now
        saved = self.sessions.save_session(session)
        self.sessions.save_runtime(
            session.id,
            elapsed_seconds=elapsed,
            remaining_seconds=max(0, session.planned_minutes * 60 - elapsed),
            last_resumed_at=None,
            scheduler_job_id=None,
            updated_at=now,
        )
        self.pomodoro_scheduler.cancel_completion(runtime.scheduler_job_id)
        return saved

    # === Phase 4 Study Library application boundary ===
    _RESOURCE_MUTABLE_FIELDS = {"title", "resource_type", "course_or_subject", "metadata"}

    @staticmethod
    def _decode_study_attachment(*, filename: str, mime_type: str, data: bytes) -> str:
        mime=(mime_type or "").lower(); suffix=Path(filename).suffix.lower()
        textual=(mime.startswith("text/") or mime in {"application/json","application/xml"} or suffix in {".txt",".md",".markdown",".json",".csv",".tsv",".xml"})
        if not textual:
            raise ValueError("Phase 4.1 can index UTF-8 text/Markdown/JSON/CSV/XML attachments; binary/PDF extraction is not enabled yet")
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("study attachment is not valid UTF-8 text") from exc

    def list_resources(self, *, course_or_subject: str = "", resource_type: str = "") -> list[StudyResource]:
        return self.repository.list_resources(course_or_subject=course_or_subject, resource_type=resource_type)

    def get_resource(self, resource_id: str) -> StudyResource:
        return self.repository.get_resource(resource_id)

    def create_resource(self, payload: dict[str, Any]) -> StudyResource:
        allowed={"attachment_id","title","resource_type","course_or_subject","metadata"}
        unknown=set(payload)-allowed
        if unknown:
            raise ValueError(f"unsupported resource fields: {', '.join(sorted(unknown))}")
        attachment_id=str(payload.get("attachment_id") or "").strip()
        if not attachment_id:
            raise ValueError("attachment_id is required")
        attachment=self.attachments.get(attachment_id)
        if attachment.status is AttachmentStatus.DELETED:
            raise ValueError("cannot create StudyResource from a deleted attachment")
        data=self.attachments.read_bytes(attachment.id)
        text=self._decode_study_attachment(filename=attachment.original_filename, mime_type=attachment.inferred_mime_type or attachment.declared_mime_type, data=data)
        raw=dict(payload)
        raw.setdefault("title", attachment.original_filename)
        raw.setdefault("resource_type", "document")
        raw.setdefault("course_or_subject", "")
        raw.setdefault("metadata", {})
        resource=StudyResource.model_validate(raw)
        saved=self.repository.save_resource(resource)
        try:
            self.library.index_resource(resource_id=saved.id, title=saved.title, course_or_subject=saved.course_or_subject, content=text)
        except Exception:
            self.repository.delete_resource(saved.id)
            raise
        return saved

    def update_resource(self, resource_id: str, patch: dict[str, Any]) -> StudyResource:
        unknown=set(patch)-self._RESOURCE_MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"unsupported resource fields: {', '.join(sorted(unknown))}")
        resource=self.repository.get_resource(resource_id)
        raw=resource.model_dump(); raw.update(patch); raw["updated_at"]=self._now()
        saved=self.repository.save_resource(StudyResource.model_validate(raw))
        self.library.update_resource_metadata(resource_id=saved.id, title=saved.title, course_or_subject=saved.course_or_subject)
        return saved

    def delete_resource(self, resource_id: str) -> None:
        self.library.delete_resource(resource_id)
        self.repository.delete_resource(resource_id)

    def get_resource_content(self, resource_id: str) -> dict[str, Any]:
        self.repository.get_resource(resource_id)
        content=self.library.get_content(resource_id)
        if content is None:
            raise ValueError("study resource has no indexed content")
        return content

    def search_resources(self, *, query: str = "", course_or_subject: str = "", resource_type: str = "", limit: int = 20) -> list[dict[str, Any]]:
        return self.library.search(query=query, course_or_subject=course_or_subject, resource_type=resource_type, limit=limit)

