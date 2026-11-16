from datetime import datetime, timedelta

import pytest

from honeyos.core.time import local_timezone
from honeyos.scheduler import jobs
from honeyos.scheduler.scheduler import run_job
from honeyos.study.markdown import export_study_plan_markdown
from honeyos.study.planning import planning_intent, planning_revision, preview_chat_plan, save_chat_plan, template_markdown
from honeyos.study.reminders import change_reminder, list_reminders
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService


@pytest.fixture
def study(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    monkeypatch.setattr(jobs, "CRON_DIR", tmp_path / "cron")
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "cron/jobs.json")
    monkeypatch.setattr(jobs, "OUTPUT_DIR", tmp_path / "cron/output")
    return StudyService(StudyRepository(tmp_path))


def test_trigger_and_template(study):
    assert planning_intent("帮我做一个21天复习计划")
    assert planning_intent("make a study plan")
    assert planning_intent("每天两个小时", [{"role": "assistant", "content": "[学习计划问卷]"}])
    revision_history = [{"role": "assistant", "content": "[学习计划调整问卷]"}]
    assert planning_intent("每天两个小时", revision_history)
    assert planning_revision("每天两个小时", revision_history)
    assert not planning_intent("你好")
    assert not planning_intent("每天下午有课")
    assert not planning_intent("我要继续聊天", [{"role": "assistant", "content": "[学习计划问卷]"}])
    markdown = template_markdown()
    assert "\nid:" not in markdown and "\n  id:" not in markdown
    imported = study.import_markdown_plan(markdown)
    assert imported.tasks and imported.source_type.value == "markdown_import"


def test_confirm_and_revision_keep_learning_history(study):
    markdown = template_markdown()
    draft, _ = preview_chat_plan(study, markdown, revision=False)
    assert not study.list_plans()
    saved = save_chat_plan(study, markdown, revision=False, plan_id=draft.id)
    assert saved.source_type.value == "honeyos_generated"
    assert save_chat_plan(study, markdown, revision=False, plan_id=draft.id).id == saved.id
    task = saved.tasks[0]
    session = study.create_session(saved.id, task.id, {"planned_minutes": 25})
    saved = study.get_plan(saved.id)
    revised = saved.model_copy(deep=True)
    revised.tasks[0].scheduled_date += timedelta(days=1)
    raw = export_study_plan_markdown(revised)
    with pytest.raises(ValueError):
        save_chat_plan(study, raw, revision=True, expected_updated_at="old")
    updated = save_chat_plan(study, raw, revision=True, expected_updated_at=saved.updated_at.isoformat())
    assert updated.tasks[0].scheduled_date == task.scheduled_date + timedelta(days=1)
    assert [item.id for item in study.list_sessions(task.id)] == [session.id]


def test_fixed_reminder_moves_and_is_cancelled_on_delete(study):
    today = datetime.now(local_timezone()).date()
    plan = study.create_plan({"title": "Practice", "start_date": today, "end_date": today + timedelta(days=6)})
    day = today + timedelta(days=2)
    plan = study.create_task(plan.id, {"title": "Chapter 1", "scheduled_date": day})
    task = plan.tasks[0]
    change_reminder(study, plan.id, task.id, "19:30", "verification-chat")
    [job] = jobs.list_jobs()
    assert job["task_kind"] == "fixed_reminder"
    assert job["origin"]["chat_id"] == "verification-chat"
    ok, output, message, error = run_job(job)
    assert ok and error is None and "zero-model" in output and "Chapter 1" in message
    assert job["next_run_at"].startswith(day.isoformat())
    assert list_reminders(study, plan.id) == {task.id: "19:30"}
    moved = day + timedelta(days=1)
    study.update_task(plan.id, task.id, {"scheduled_date": moved})
    [updated] = jobs.list_jobs()
    assert updated["id"] == job["id"]
    assert updated["next_run_at"].startswith(moved.isoformat())
    study.delete_plan(plan.id)
    assert not jobs.list_jobs(include_disabled=True)
    assert not study.list_plans()
