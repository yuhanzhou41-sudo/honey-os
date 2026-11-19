"""Project persisted HoneyOS records into content-free event envelopes."""

from datetime import datetime

from .store import Event, Source, UTC


def chat_events(session_id, messages):
    for message in messages:
        if message["role"] in {"user", "assistant"} and message.get("active", True):
            yield Event(
                Source.CHAT, (session_id, str(message["id"])),
                "message." + message["role"],
                datetime.fromtimestamp(message["timestamp"], UTC),
            )


def study_events(plan):
    for task in plan.tasks:
        yield Event(
            Source.STUDY, (plan.id, task.id), "task." + task.status.value,
            task.updated_at,
        )


def reminder_events(jobs):
    for job in jobs:
        if job.get("task_kind") != "fixed_reminder":
            continue
        yield Event(
            Source.REMINDER, (job["id"],), "reminder.created",
            datetime.fromisoformat(job["created_at"]),
        )
        if job.get("last_run_at"):
            yield Event(
                Source.REMINDER, (job["id"],), "reminder.run",
                datetime.fromisoformat(job["last_run_at"]),
            )
