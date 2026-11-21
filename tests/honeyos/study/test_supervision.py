from datetime import datetime, timedelta, timezone

import pytest

from honeyos.study import supervision
from honeyos.study.models import StudyPlan
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService
from honeyos.study.supervision import ReminderSettings, StudyReminders

LOCAL = timezone(timedelta(hours=8))


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    study = StudyService(StudyRepository(tmp_path))
    now = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)  # 18:00 in Asia/Shanghai
    monkeypatch.setattr(study, "_now", lambda: now)
    plans = [
        study.repository.save_new_plan(StudyPlan(
            title=name, status="active", start_date="2026-11-20", end_date="2026-11-22",
            tasks=[
                {"title": "Task A", "scheduled_date": "2026-11-20", "planned_minutes": 25},
                {"title": "Task B", "scheduled_date": "2026-11-20", "planned_minutes": 25},
            ],
        ))
        for name in ("皮肤性病学", "药理学")
    ]
    return StudyReminders(study), plans


def test_settings_defaults_and_validation(store):
    reminders, plans = store
    plan_id = plans[0].id
    default = reminders.settings(plan_id)
    assert default.enabled is False
    assert default.effective_times() == ["18:00", "21:00"]

    summary = reminders.configure(plan_id, {"enabled": True, "mode": "gentle"})
    assert summary["settings"]["times"] == ["20:00"]
    assert summary["sent_total"] == 0

    with pytest.raises(ValueError):
        reminders.configure(plan_id, {"enabled": True, "mode": "custom", "times": []})
    with pytest.raises(ValueError):
        reminders.configure(plan_id, {"enabled": True, "mode": "standard", "times": ["25:00"]})
    with pytest.raises(ValueError):
        reminders.configure(plan_id, {"enabled": True, "mode": "nope"})


def test_settings_are_per_plan(store):
    reminders, plans = store
    reminders.configure(plans[0].id, {"enabled": True, "mode": "strong"})
    assert reminders.settings(plans[1].id).enabled is False
    assert reminders.settings(plans[1].id).effective_times() == ["18:00", "21:00"]


def test_facts_ignore_disabled_finished_and_out_of_range_plans(store):
    reminders, plans = store
    plan_id = plans[0].id
    now = reminders.study._now()
    assert reminders.facts(plan_id, now) is None

    reminders.configure(plan_id, {"enabled": True, "mode": "standard"})
    facts = reminders.facts(plan_id, now)
    assert facts["tasks"] == 2 and facts["completed"] == 0
    assert facts["kind"] == "not_started"
    assert reminders.facts(plan_id, now + timedelta(days=3)) is None

    with reminders.study.repository._connect() as db:
        db.execute("UPDATE study_tasks SET status='completed' WHERE plan_id=?", (plan_id,))
    assert reminders.facts(plan_id, now) is None


def test_run_due_sends_once_per_slot_and_escalates_tone(store, monkeypatch):
    reminders, plans = store
    plan_id = plans[0].id
    reminders.configure(plan_id, {"enabled": True, "mode": "strong"})
    tones = []

    def fake_send(title, message):
        tones.append((title, message))
        return True

    monkeypatch.setattr(supervision.notify, "available", lambda: True)
    monkeypatch.setattr(supervision.notify, "send", fake_send)

    def message(facts, tone):
        return str(tone)

    monkeypatch.setattr(reminders, "message", message)
    day = datetime(2026, 11, 20, tzinfo=LOCAL)
    assert reminders.run_due(day.replace(hour=12)) == 1
    assert reminders.run_due(day.replace(hour=12, minute=1)) == 0
    assert reminders.run_due(day.replace(hour=12, minute=20)) == 0  # outside catch-up window
    assert reminders.run_due(day.replace(hour=18)) == 1
    assert reminders.run_due(day.replace(hour=21, minute=30)) == 1
    assert reminders.summary(plan_id)["sent_today"] == 3
    assert reminders.summary(plan_id)["sent_total"] == 3
    assert [tone for _, tone in tones] == ["0", "1", "2"]
    assert all(title.startswith("该学习了") for title, _ in tones)


def test_message_keeps_local_model_but_rejects_invented_numbers(store, monkeypatch):
    reminders, _ = store
    facts = {
        "completed": 0, "tasks": 2, "kind": "not_started",
        "title": "皮肤性病学", "next_task": "Task A",
    }

    def fake_generate(system, content, **kwargs):
        return '{"advice":"先打开课件，别急着做笔记。"}'

    monkeypatch.setattr("honeyos.study.local_model._generate", fake_generate)
    assert "先打开课件" in reminders.message(facts, 0)

    monkeypatch.setattr(
        "honeyos.study.local_model._generate",
        lambda system, content, **kwargs: '{"advice":"已完成 3 项，继续。"}',
    )
    assert "已完成" not in reminders.message(facts, 0)
    assert "今天 0/2 项完成" in reminders.message(facts, 2)


def test_message_falls_back_when_local_model_is_unavailable(store, monkeypatch):
    reminders, _ = store
    facts = {"completed": 1, "tasks": 2, "kind": "pending", "title": "皮肤性病学"}

    def boom(system, content, **kwargs):
        raise RuntimeError("model offline")

    monkeypatch.setattr("honeyos.study.local_model._generate", boom)
    assert reminders.message(facts, 1).startswith("今天 1/2 项完成")
