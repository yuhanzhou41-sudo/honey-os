from datetime import date, datetime, timedelta, timezone

import pytest

from honeyos.study import StudyRepository, StudyService
from honeyos.study.models import StudySessionStatus


class FakePomodoroScheduler:
    def __init__(self):
        self.created = []
        self.cancelled = []

    def schedule_completion(self, session_id, run_at):
        job_id = f"job-{len(self.created)+1}"
        self.created.append((job_id, session_id, run_at))
        return job_id

    def cancel_completion(self, job_id):
        if job_id:
            self.cancelled.append(job_id)


def _service(tmp_path):
    fake = FakePomodoroScheduler()
    service = StudyService(StudyRepository(tmp_path), pomodoro_scheduler=fake)
    plan = service.create_plan(
        {
            "title": "Phase 3",
            "start_date": date(2026, 9, 21),
            "end_date": date(2026, 9, 22),
            "focus_minutes": 25,
        }
    )
    plan = service.create_task(
        plan.id,
        {
            "title": "Pomodoro task",
            "scheduled_date": date(2026, 9, 21),
            "planned_minutes": 40,
        },
    )
    return service, fake, plan, plan.tasks[0]


def test_pomodoro_full_lifecycle_uses_server_timestamps(tmp_path):
    service, fake, plan, task = _service(tmp_path)
    clock = {"now": datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)}
    service._now = lambda: clock["now"]

    session = service.create_session(plan.id, task.id, {"planned_minutes": 25})
    assert session.status is StudySessionStatus.PLANNED

    session = service.start_session(session.id)
    assert session.status is StudySessionStatus.RUNNING
    assert session.started_at == clock["now"]
    assert session.expected_end_at == clock["now"] + timedelta(minutes=25)
    assert len(fake.created) == 1

    clock["now"] += timedelta(minutes=7, seconds=20)
    session = service.pause_session(session.id)
    assert session.status is StudySessionStatus.PAUSED
    assert session.expected_end_at is None
    assert fake.cancelled == ["job-1"]

    clock["now"] += timedelta(minutes=2)
    session = service.resume_session(session.id)
    assert session.status is StudySessionStatus.RUNNING
    assert len(fake.created) == 2

    clock["now"] += timedelta(minutes=3)
    session = service.complete_session(session.id)
    assert session.status is StudySessionStatus.COMPLETED
    assert session.ended_at == clock["now"]
    assert session.actual_minutes == 10
    assert fake.cancelled[-1] == "job-2"


def test_scheduled_completion_uses_backend_expected_end(tmp_path):
    service, fake, plan, task = _service(tmp_path)
    clock = {"now": datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)}
    service._now = lambda: clock["now"]

    session = service.create_session(plan.id, task.id, {"planned_minutes": 1})
    session = service.start_session(session.id)
    due = session.expected_end_at
    assert due is not None

    clock["now"] = due + timedelta(seconds=40)
    completed = service.complete_session(session.id, scheduled=True)
    assert completed.status is StudySessionStatus.COMPLETED
    assert completed.ended_at == due
    assert completed.actual_minutes == 1


def test_due_session_reconciles_even_if_scheduler_was_late(tmp_path):
    service, fake, plan, task = _service(tmp_path)
    clock = {"now": datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)}
    service._now = lambda: clock["now"]
    session = service.create_session(plan.id, task.id, {"planned_minutes": 1})
    service.start_session(session.id)
    clock["now"] += timedelta(minutes=2)
    assert service.get_session(session.id).status is StudySessionStatus.COMPLETED


def test_invalid_session_transitions_are_rejected(tmp_path):
    service, fake, plan, task = _service(tmp_path)
    session = service.create_session(plan.id, task.id, {})
    with pytest.raises(ValueError):
        service.pause_session(session.id)
    service.start_session(session.id)
    with pytest.raises(ValueError):
        service.start_session(session.id)


def test_session_persists_in_canonical_study_database(tmp_path):
    service, fake, plan, task = _service(tmp_path)
    session = service.create_session(plan.id, task.id, {"planned_minutes": 12})
    second = StudyService(
        StudyRepository(tmp_path),
        pomodoro_scheduler=FakePomodoroScheduler(),
    )
    loaded = second.get_session(session.id)
    assert loaded.id == session.id
    assert loaded.task_id == task.id
    assert loaded.planned_minutes == 12
