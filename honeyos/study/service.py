from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
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
from .local_source import (
    DOCUMENT_FORMATS,
    TEXT_FORMATS,
    extract_local_source,
    local_source_metadata,
    local_source_status,
    resolve_local_source,
    source_signature,
)
from honeyos.files.models import AttachmentStatus
from honeyos.files.service import AttachmentService
from .repository import (
    StudyPlanNotFoundError,
    StudyRepository,
    StudyResourceNotFoundError,
)
from .session_store import StudySessionNotFoundError, StudySessionStore
from .markdown import StudyPlanMarkdownError, parse_study_plan_markdown
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
        local_mount_root: Path | str = "/mnt",
    ):
        self.repository = repository or StudyRepository()
        self.sessions = session_store or StudySessionStore(self.repository.db_path)
        self.pomodoro_scheduler = pomodoro_scheduler or StudyPomodoroScheduler()
        self.library = StudyLibraryIndex(self.repository.db_path)
        self.attachments = AttachmentService(self.repository.study_dir.parent / "files")
        self.local_mount_root = Path(local_mount_root)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def list_plans(self) -> list[StudyPlan]:
        return self.repository.list_plans()

    def get_plan(self, plan_id: str) -> StudyPlan:
        return self.repository.get_plan(plan_id)

    def preview_markdown_plan(self, markdown_text: str) -> StudyPlan:
        """Parse and validate StudyPlan Markdown without persistence."""
        if not isinstance(markdown_text, str) or not markdown_text.strip():
            raise StudyPlanMarkdownError("markdown must be a non-empty string")

        plan = parse_study_plan_markdown(markdown_text)
        raw = plan.model_dump()
        raw["source_type"] = StudyPlanSource.MARKDOWN_IMPORT.value
        return validate_study_plan(raw)

    def import_markdown_plan(self, markdown_text: str) -> StudyPlan:
        """Persist a previously previewable Markdown plan through StudyRepository."""
        plan = self.preview_markdown_plan(markdown_text)

        try:
            self.repository.get_plan(plan.id)
        except StudyPlanNotFoundError:
            pass
        else:
            raise ValueError(
                "study plan id already exists; remove the id from the Markdown "
                "or import a plan with a different id"
            )

        return self.repository.save_plan(plan)

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
        from .reminders import sync_plan_reminders

        saved = self.repository.save_plan(validate_study_plan(raw))
        sync_plan_reminders(self, saved, plan)
        return saved

    def delete_plan(self, plan_id: str) -> None:
        from .reminders import cancel_task_reminders

        plan = self.get_plan(plan_id)
        cancel_task_reminders(self, [task.id for task in plan.tasks])
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
            from .reminders import sync_plan_reminders

            before = plan.model_copy(deep=True)
            plan.tasks[index] = StudyTask.model_validate(raw)
            plan.updated_at = self._now()
            saved = self.repository.save_plan(validate_study_plan(plan))
            sync_plan_reminders(self, saved, before)
            return saved
        raise StudyTaskNotFoundError(task_id)

    def set_task_status(self, plan_id: str, task_id: str, status: str) -> StudyPlan:
        return self.update_task(plan_id, task_id, {"status": status})

    def delete_task(self, plan_id: str, task_id: str) -> StudyPlan:
        plan = self.repository.get_plan(plan_id)
        remaining = [task for task in plan.tasks if task.id != task_id]
        if len(remaining) == len(plan.tasks):
            raise StudyTaskNotFoundError(task_id)
        from .reminders import cancel_task_reminders

        cancel_task_reminders(self, [task_id])
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
        if textual:
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("study attachment is not valid UTF-8 text") from exc

        if suffix not in {".pdf", ".docx", ".pptx", ".xlsx"}:
            raise ValueError(
                "unsupported study attachment type; supported formats are "
                "TXT/Markdown/JSON/CSV/TSV/XML/PDF/DOCX/PPTX/XLSX"
            )

        from honeyos.tools.read_extract import ExtractionError, extract_document_text

        try:
            with tempfile.NamedTemporaryFile(suffix=suffix) as handle:
                handle.write(data)
                handle.flush()
                text=extract_document_text(handle.name)
        except ExtractionError as exc:
            message=str(exc)
            if "no extractable text" in message.lower():
                raise ValueError(
                    f"no extractable text found in {filename}; scanned/image-only "
                    "documents require a later OCR phase"
                ) from exc
            raise ValueError(
                f"study document extraction failed for {filename}: {message}"
            ) from exc

        if not text.strip():
            raise ValueError(f"no extractable text found in {filename}")
        return text

    def list_resources(self, *, course_or_subject: str = "", resource_type: str = "") -> list[StudyResource]:
        return self.repository.list_resources(course_or_subject=course_or_subject, resource_type=resource_type)

    def get_resource(self, resource_id: str) -> StudyResource:
        return self.repository.get_resource(resource_id)

    def reference_local_file(self, filename: str, *, resource_id: str = "") -> tuple[StudyResource, bool]:
        path = resolve_local_source(filename, self.local_mount_root)
        if path.suffix.lower() not in TEXT_FORMATS | DOCUMENT_FORMATS:
            raise ValueError("不支持此文档格式")
        signature = source_signature(path)
        source = local_source_metadata(path, self.attachments.max_attachment_bytes)
        digest = source["sha256"]
        if resource_id:
            with self.repository.resource_transaction() as conn:
                if signature != source_signature(path):
                    raise ValueError("原文件发生变化，请重试")
                resource = self.repository.get_resource(resource_id, connection=conn)
                previous = resource.metadata.get("local_source")
                if not previous or previous.get("sha256") != digest:
                    raise ValueError("重新定位时请选择与原资料内容一致的文件")
                return self._save_local_location(resource, source, conn), True

        matching_attachments = [
            item.id for item in self.attachments.repository.find_by_sha256(digest)
            if item.status is AttachmentStatus.READY
        ]

        def existing(conn):
            resource = self.repository.find_resource_by_local_digest(digest, connection=conn)
            if resource is not None:
                if local_source_status(resource.metadata["local_source"]) != "online":
                    resource = self._save_local_location(resource, source, conn)
                return resource
            legacy = self.repository.find_indexed_resource_by_attachments(matching_attachments, connection=conn)
            return self._save_local_location(legacy, source, conn) if legacy is not None else None

        # Repeated references hash the selected file but skip extraction.
        with self.repository.resource_transaction() as conn:
            if signature != source_signature(path):
                raise ValueError("原文件发生变化，请重试")
            match = existing(conn)
            if match is not None:
                return match, True

        text = extract_local_source(path)
        if not text.strip():
            raise ValueError("没有可引用的正文")
        if signature != source_signature(path):
            raise ValueError("提取过程中原文件发生变化，请重试")

        # The second lookup and all writes share one transaction across workers.
        with self.repository.resource_transaction() as conn:
            if signature != source_signature(path):
                raise ValueError("原文件发生变化，请重试")
            match = existing(conn)
            if match is not None:
                return match, True
            resource = StudyResource(
                attachment_id="",
                title=path.name,
                resource_type="document",
                metadata={"local_source": source},
            )
            self.repository.save_resource(resource, connection=conn)
            self.library.index_resource(
                resource_id=resource.id, title=resource.title, course_or_subject="",
                content=text, connection=conn,
            )
        return resource, False

    def _save_local_location(self, resource: StudyResource, source: dict, connection) -> StudyResource:
        updated = resource.model_copy(update={
            "metadata": {**resource.metadata, "local_source": source},
            "updated_at": self._now(),
        })
        return self.repository.save_resource(updated, connection=connection)

    def describe_resource_storage(self, resource: StudyResource) -> dict[str, Any]:
        source = resource.metadata.get("local_source")
        content = self.library.get_content(resource.id)
        return {
            "source_path": source["path"] if source else None,
            "source_status": local_source_status(source) if source else "managed",
            "original_bytes": source["size_bytes"] if source else None,
            "indexed_text_bytes": len(content["extracted_text"].encode("utf-8")) if content else 0,
            "has_managed_attachment": bool(resource.attachment_id),
        }

    def build_chat_resource_context(self, resource_ids: list[str]) -> str:
        remaining = 12_000
        excerpts = []
        for resource_id in dict.fromkeys(resource_ids):
            resource = self.get_resource(resource_id)
            source = resource.metadata.get("local_source")
            if source and local_source_status(source) != "online":
                raise ValueError(f"原文件已更改或暂不可访问：{resource.title}。请在资料库重新定位。")
            content = self.get_resource_content(resource_id)["extracted_text"].strip()
            if not content:
                raise ValueError(f"资料没有可引用的正文：{resource.title}")
            excerpt = content[:remaining]
            remaining -= len(excerpt)
            note = "（仅引用部分正文）" if len(excerpt) < len(content) else ""
            excerpts.append(f"资料：{resource.title} [{resource.id}]{note}\n{excerpt}")
        return "\n\n".join(excerpts)

    def create_resource(self, payload: dict[str, Any]) -> StudyResource:
        allowed={"attachment_id","title","resource_type","course_or_subject","metadata"}
        unknown=set(payload)-allowed
        if unknown:
            raise ValueError(f"unsupported resource fields: {', '.join(sorted(unknown))}")
        if isinstance(payload.get("metadata"), dict) and "local_source" in payload["metadata"]:
            raise ValueError("local_source is managed by Study")
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
        if "metadata" in patch:
            if not isinstance(patch["metadata"], dict) or "local_source" in patch["metadata"]:
                raise ValueError("local_source is managed by Study")
            if "local_source" in resource.metadata:
                patch = {**patch, "metadata": {**patch["metadata"], "local_source": resource.metadata["local_source"]}}
        raw=resource.model_dump(); raw.update(patch); raw["updated_at"]=self._now()
        saved=self.repository.save_resource(StudyResource.model_validate(raw))
        self.library.update_resource_metadata(resource_id=saved.id, title=saved.title, course_or_subject=saved.course_or_subject)
        return saved

    def delete_resource(self, resource_id: str) -> None:
        with self.repository.resource_transaction() as conn:
            self.library.delete_resource(resource_id, connection=conn)
            self.repository.delete_resource(resource_id, connection=conn)

    def get_resource_content(self, resource_id: str) -> dict[str, Any]:
        self.repository.get_resource(resource_id)
        content=self.library.get_content(resource_id)
        if content is None:
            raise ValueError("study resource has no indexed content")
        return content

    def search_resources(self, *, query: str = "", course_or_subject: str = "", resource_type: str = "", limit: int = 20) -> list[dict[str, Any]]:
        return self.library.search(query=query, course_or_subject=course_or_subject, resource_type=resource_type, limit=limit)

