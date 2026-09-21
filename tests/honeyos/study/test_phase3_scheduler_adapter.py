from datetime import datetime, timezone

from honeyos.study.pomodoro import StudyPomodoroScheduler


def test_scheduler_adapter_uses_safe_relative_no_agent_wrapper(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr("honeyos.study.pomodoro.get_honeyos_home", lambda: tmp_path)

    def fake_create_job(**kwargs):
        captured.update(kwargs)
        return {"id": "cron-study-1"}

    monkeypatch.setattr("honeyos.study.pomodoro.create_job", fake_create_job)

    scheduler = StudyPomodoroScheduler()
    monkeypatch.setattr(scheduler, "_notify", lambda: None)

    job_id = scheduler.schedule_completion(
        "session_abc",
        datetime(2026, 9, 21, 12, 25, tzinfo=timezone.utc),
    )

    assert job_id == "cron-study-1"
    assert captured["no_agent"] is True
    assert captured["repeat"] is False
    assert captured["script"] == "study-pomodoro-session_abc.sh"

    wrapper = tmp_path / "scripts" / captured["script"]
    assert wrapper.is_file()
    text = wrapper.read_text(encoding="utf-8")
    assert "pomodoro_runner complete session_abc" in text


def test_cancel_removes_safe_wrapper(monkeypatch, tmp_path):
    monkeypatch.setattr("honeyos.study.pomodoro.get_honeyos_home", lambda: tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    wrapper = scripts / "study-pomodoro-session_abc.sh"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(
        "honeyos.study.pomodoro.get_job",
        lambda job_id: {"id": job_id, "script": wrapper.name},
    )
    monkeypatch.setattr("honeyos.study.pomodoro.remove_job", lambda job_id: True)

    scheduler = StudyPomodoroScheduler()
    monkeypatch.setattr(scheduler, "_notify", lambda: None)
    scheduler.cancel_completion("cron-study-1")

    assert not wrapper.exists()
