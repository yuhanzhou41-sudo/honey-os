from __future__ import annotations

import re
from datetime import date
from typing import Any

import yaml

from .models import SUPPORTED_STUDY_PLAN_VERSIONS, StudyPlan, StudyPlanSource, StudyTask
from .validation import StudyPlanValidationError, validate_study_plan


_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(?P<yaml>.*?)\n---\s*(?:\n|$)",
    re.DOTALL,
)

_DATE_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
_TASK_RE = re.compile(r"^-\s+\[( |x|X)\]\s+(.+?)\s*$")
_META_RE = re.compile(r"^\s{2,}([A-Za-z_]+):\s*(.*?)\s*$")


class StudyPlanMarkdownError(ValueError):
    pass


def _bool_value(value: str) -> bool:
    normalized = value.strip().lower()

    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False

    raise StudyPlanMarkdownError(f"invalid boolean value: {value!r}")


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = _FRONTMATTER_RE.search(text)

    if not match:
        raise StudyPlanMarkdownError(
            "StudyPlan Markdown must begin with YAML front matter"
        )

    try:
        data = yaml.safe_load(match.group("yaml")) or {}
    except yaml.YAMLError as exc:
        raise StudyPlanMarkdownError(f"invalid YAML front matter: {exc}") from exc

    if not isinstance(data, dict):
        raise StudyPlanMarkdownError("front matter must contain a YAML mapping")

    return data, text[match.end():]


def parse_study_plan_markdown(text: str) -> StudyPlan:
    front, body = _frontmatter(text)

    version = front.get("study_plan_version")
    if type(version) is not int or version not in SUPPORTED_STUDY_PLAN_VERSIONS:
        raise StudyPlanMarkdownError(
            f"unsupported study_plan_version: {version!r}"
        )

    allowed_fields = {
        "study_plan_version", "id", "title", "description", "start_date",
        "end_date", "status", "focus_minutes", "break_minutes",
        "long_break_minutes", "long_break_after_sessions", "source_type",
    }
    if version == 2:
        allowed_fields.add("flex_slots")
    unknown_fields = set(front) - allowed_fields
    if unknown_fields:
        raise StudyPlanMarkdownError(
            "unsupported front matter fields: "
            + ", ".join(sorted(str(key) for key in unknown_fields))
        )

    goals: list[str] = []
    tasks: list[StudyTask] = []

    section: str | None = None
    current_date: date | None = None
    current_task: dict[str, Any] | None = None

    def flush_task() -> None:
        nonlocal current_task

        if current_task is None:
            return

        if current_date is None:
            raise StudyPlanMarkdownError(
                "task appears before a schedule date heading"
            )

        current_task["scheduled_date"] = current_date
        current_task.setdefault("planned_minutes", front.get("focus_minutes", 40))
        current_task.setdefault("review_required", False)
        current_task.setdefault("description", "")
        current_task.setdefault("order_index", len(tasks) + 1)

        tasks.append(StudyTask.model_validate(current_task))
        current_task = None

    for raw_line in body.splitlines():
        line = raw_line.rstrip()

        if line == "# Goals":
            flush_task()
            section = "goals"
            current_date = None
            continue

        if line == "# Schedule":
            flush_task()
            section = "schedule"
            current_date = None
            continue

        date_match = _DATE_HEADER_RE.match(line)
        if section == "schedule" and date_match:
            flush_task()
            try:
                current_date = date.fromisoformat(date_match.group(1))
            except ValueError as exc:
                raise StudyPlanMarkdownError(
                    f"invalid schedule date: {date_match.group(1)!r}"
                ) from exc
            continue

        task_match = _TASK_RE.match(line)
        if section == "schedule" and task_match:
            flush_task()

            if current_date is None:
                raise StudyPlanMarkdownError(
                    "task appears before a schedule date heading"
                )

            checked = task_match.group(1).lower() == "x"

            current_task = {
                "title": task_match.group(2).strip(),
                "scheduled_date": current_date,
                "status": "completed" if checked else "planned",
            }
            continue

        meta_match = _META_RE.match(line)
        if section == "schedule" and current_task is not None and meta_match:
            key, value = meta_match.groups()

            if key == "duration":
                try:
                    current_task["planned_minutes"] = int(value)
                except ValueError as exc:
                    raise StudyPlanMarkdownError(
                        f"duration must be an integer: {value!r}"
                    ) from exc
            elif version == 2 and key in {"priority", "kind"}:
                current_task[key] = value
            elif version == 2 and key == "minimum_required":
                current_task[key] = _bool_value(value)
            elif key == "review":
                current_task["review_required"] = _bool_value(value)
            elif key == "id":
                current_task["id"] = value
            elif key == "description":
                current_task["description"] = value
            elif key == "status":
                current_task["status"] = value
            elif key == "order":
                try:
                    current_task["order_index"] = int(value)
                except ValueError as exc:
                    raise StudyPlanMarkdownError(
                        f"order must be an integer: {value!r}"
                    ) from exc
            else:
                raise StudyPlanMarkdownError(
                    f"unsupported task metadata field: {key!r}"
                )
            continue

        if section == "goals" and line.startswith("- "):
            goals.append(line[2:].strip())
            continue

        if not line.strip():
            continue

    flush_task()

    raw_plan = {
        "id": front.get("id"),
        "schema_version": version,
        "title": front.get("title"),
        "description": front.get("description", ""),
        "start_date": front.get("start_date"),
        "end_date": front.get("end_date"),
        "status": front.get("status", "draft"),
        "focus_minutes": front.get("focus_minutes", 40),
        "break_minutes": front.get("break_minutes", 10),
        "long_break_minutes": front.get("long_break_minutes", 25),
        "long_break_after_sessions": front.get(
            "long_break_after_sessions",
            3,
        ),
        "source_type": front.get(
            "source_type",
            StudyPlanSource.MARKDOWN_IMPORT.value,
        ),
        "goals": goals,
        "tasks": [task.model_dump() for task in tasks],
        "flex_slots": front.get("flex_slots", []),
    }

    if raw_plan["id"] is None:
        raw_plan.pop("id")

    try:
        return validate_study_plan(raw_plan)
    except StudyPlanValidationError as exc:
        raise StudyPlanMarkdownError(str(exc)) from exc


def export_study_plan_markdown(plan: StudyPlan, *, include_ids: bool = True) -> str:
    plan = validate_study_plan(plan)

    front = {
        "study_plan_version": plan.schema_version,
        "id": plan.id,
        "title": plan.title,
        "description": plan.description,
        "start_date": plan.start_date.isoformat(),
        "end_date": plan.end_date.isoformat(),
        "status": plan.status.value,
        "source_type": plan.source_type.value,
        "focus_minutes": plan.focus_minutes,
        "break_minutes": plan.break_minutes,
        "long_break_minutes": plan.long_break_minutes,
        "long_break_after_sessions": plan.long_break_after_sessions,
    }

    if plan.schema_version == 2:
        front["flex_slots"] = [
            slot.model_dump(mode="json", exclude=set() if include_ids else {"id"})
            for slot in plan.flex_slots
        ]

    if not include_ids:
        front.pop("id")

    parts = [
        "---",
        yaml.safe_dump(
            front,
            allow_unicode=True,
            sort_keys=False,
        ).rstrip(),
        "---",
        "",
        "# Goals",
    ]

    for goal in plan.goals:
        parts.append(f"- {goal}")

    parts.extend(["", "# Schedule"])

    dates = sorted({task.scheduled_date for task in plan.tasks})

    for scheduled_date in dates:
        parts.extend(["", f"## {scheduled_date.isoformat()}", ""])

        day_tasks = sorted(
            (
                task
                for task in plan.tasks
                if task.scheduled_date == scheduled_date
            ),
            key=lambda task: task.order_index,
        )

        for task in day_tasks:
            checked = "x" if task.status.value == "completed" else " "
            parts.append(f"- [{checked}] {task.title}")
            if include_ids:
                parts.append(f"  id: {task.id}")
            parts.append(f"  duration: {task.planned_minutes}")
            parts.append(
                f"  review: {'true' if task.review_required else 'false'}"
            )
            parts.append(f"  status: {task.status.value}")
            parts.append(f"  order: {task.order_index}")
            if plan.schema_version == 2:
                parts.append(f"  priority: {task.priority}")
                parts.append(f"  minimum_required: {str(task.minimum_required).lower()}")
                parts.append(f"  kind: {task.kind}")

            if task.description:
                safe_description = " ".join(task.description.splitlines())
                parts.append(f"  description: {safe_description}")

            parts.append("")

    return "\n".join(parts).rstrip() + "\n"
