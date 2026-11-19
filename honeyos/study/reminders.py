"""Persist Study reminder choices and schedule fixed web-session delivery."""

from contextlib import closing
from datetime import datetime, time
import re
from threading import RLock

from honeyos.core.time import local_timezone
from honeyos.scheduler.jobs import create_job, remove_job, update_job

_LOCK = RLock()


def _connect(study):
    db = study.repository._connect()
    db.execute("""CREATE TABLE IF NOT EXISTS study_task_reminders (
        task_id TEXT PRIMARY KEY REFERENCES study_tasks(id) ON DELETE CASCADE,
        time TEXT NOT NULL, session_id TEXT NOT NULL, job_id TEXT
    )""")
    return db


def _read(db, task_id):
    return db.execute("SELECT * FROM study_task_reminders WHERE task_id=?", (task_id,)).fetchone()


def _when(task, value):
    return datetime.combine(task.scheduled_date, time.fromisoformat(value), tzinfo=local_timezone())


def _notify():
    from honeyos.tools.cronjob_tools import _notify_provider_jobs_changed_safe
    _notify_provider_jobs_changed_safe()


def _apply(plan, task, value, session_id, old_job=None):
    when = _when(task, value)
    eligible = (
        plan.status.value not in {"paused", "completed", "archived"}
        and task.status.value not in {"completed", "skipped", "cancelled"}
        and when > datetime.now(local_timezone())
    )
    if not eligible:
        if old_job:
            remove_job(old_job)
        return None
    title = " ".join(task.title.split()).replace("MEDIA:", "MEDIA：")
    reminder = f"该学习了：{title}（计划 {task.planned_minutes} 分钟）。"
    origin = {"platform": "api_server", "chat_id": session_id}
    schedule = when.isoformat()
    if old_job:
        job = update_job(old_job, {
            "schedule": schedule, "reminder_text": reminder, "origin": origin,
            "enabled": True,
        })
        if job:
            return old_job
    return create_job(
        prompt="", schedule=schedule, name=f"Study task {task.id}", repeat=1,
        deliver="origin", origin=origin, attach_to_session=False,
        task_kind="fixed_reminder", reminder_text=reminder,
    )["id"]


def change_reminder(study, plan_id, task_id, value, session_id=""):
    with _LOCK, closing(_connect(study)) as db, db:
        plan, task = study._get_task(plan_id, task_id)
        existing = _read(db, task_id)
        if value is None:
            if existing and existing["job_id"]:
                remove_job(existing["job_id"])
            db.execute("DELETE FROM study_task_reminders WHERE task_id=?", (task_id,))
        else:
            if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
                raise ValueError("请输入有效的提醒时刻。")
            if _when(task, value) <= datetime.now(local_timezone()):
                raise ValueError("请选择还未到的时间。")
            job = _apply(plan, task, value, session_id, existing["job_id"] if existing else None)
            if job is None:
                raise ValueError("请先启用此计划或将任务设为待执行。")
            db.execute("""INSERT INTO study_task_reminders VALUES(?,?,?,?)
                          ON CONFLICT(task_id) DO UPDATE SET time=excluded.time,
                            session_id=excluded.session_id, job_id=excluded.job_id""",
                       (task_id, value, session_id, job))
    _notify()


def list_reminders(study, plan_id):
    study.get_plan(plan_id)
    with _LOCK, closing(_connect(study)) as db:
        rows = db.execute("""SELECT r.task_id, r.time FROM study_task_reminders r
                             JOIN study_tasks t ON t.id=r.task_id WHERE t.plan_id=?""", (plan_id,))
        return {row["task_id"]: row["time"] for row in rows}


def cancel_task_reminders(study, task_ids):
    with _LOCK, closing(_connect(study)) as db, db:
        for task_id in task_ids:
            row = _read(db, task_id)
            if row and row["job_id"]:
                remove_job(row["job_id"])
    _notify()


def sync_plan_reminders(study, plan, previous):
    old = {task.id: task for task in previous.tasks}
    with _LOCK, closing(_connect(study)) as db, db:
        changed = False
        for task in plan.tasks:
            before = old.get(task.id)
            if before and plan.status == previous.status and (
                task.title, task.planned_minutes, task.scheduled_date, task.status,
            ) == (before.title, before.planned_minutes, before.scheduled_date, before.status):
                continue
            row = _read(db, task.id)
            if row:
                job = _apply(plan, task, row["time"], row["session_id"], row["job_id"])
                db.execute("UPDATE study_task_reminders SET job_id=? WHERE task_id=?", (job, task.id))
                changed = True
    if changed:
        _notify()
