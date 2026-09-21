from datetime import date

import pytest

from honeyos.study import StudyRepository, StudyService
from honeyos.study.models import StudySessionStatus, StudySessionType


class FakePomodoroScheduler:
    def __init__(self):
        self.created = []
        self.cancelled = []

    def schedule_completion(self, session_id, run_at):
        job_id = f"job-{len(self.created) + 1}"
        self.created.append((job_id, session_id, run_at))
        return job_id

    def cancel_completion(self, job_id):
        if job_id:
            self.cancelled.append(job_id)


def make_service(tmp_path):
    scheduler = FakePomodoroScheduler()
    service = StudyService(StudyRepository(tmp_path), pomodoro_scheduler=scheduler)
    plan = service.create_plan({
        "title": "Classic Pomodoro",
        "start_date": date(2026, 9, 22),
        "end_date": date(2026, 9, 22),
    })
    plan = service.create_task(plan.id, {
        "title": "Task A",
        "scheduled_date": date(2026, 9, 22),
    })
    plan = service.create_task(plan.id, {
        "title": "Task B",
        "scheduled_date": date(2026, 9, 22),
    })
    return service, plan, plan.tasks[0], plan.tasks[1]


def finish_planned(service, session):
    completed = service.complete_session(session.id)
    assert completed.status is StudySessionStatus.COMPLETED
    return completed


def test_new_plan_uses_classic_pomodoro_defaults(tmp_path):
    service, plan, task_a, _ = make_service(tmp_path)
    assert plan.focus_minutes == 25
    assert plan.break_minutes == 5
    assert plan.long_break_minutes == 15
    assert plan.long_break_after_sessions == 4
    assert task_a.planned_minutes == 25
    state = service.get_pomodoro_state(plan.id)
    assert state["next_session_type"] == StudySessionType.FOCUS.value
    assert state["next_minutes"] == 25
    assert state["focuses_in_cycle"] == 0


def test_focus_is_followed_by_short_break(tmp_path):
    service, plan, task_a, _ = make_service(tmp_path)
    focus = service.create_session(plan.id, task_a.id, {})
    assert focus.session_type is StudySessionType.FOCUS
    assert focus.planned_minutes == 25
    finish_planned(service, focus)
    state = service.get_pomodoro_state(plan.id)
    assert state["next_session_type"] == StudySessionType.SHORT_BREAK.value
    assert state["next_minutes"] == 5
    assert state["focuses_in_cycle"] == 1
    short_break = service.create_session(plan.id, task_a.id, {})
    assert short_break.session_type is StudySessionType.SHORT_BREAK
    assert short_break.planned_minutes == 5
    finish_planned(service, short_break)
    state = service.get_pomodoro_state(plan.id)
    assert state["next_session_type"] == StudySessionType.FOCUS.value
    assert state["next_minutes"] == 25


def test_fourth_focus_is_followed_by_long_break_across_tasks(tmp_path):
    service, plan, task_a, task_b = make_service(tmp_path)
    for index in range(4):
        task = task_a if index % 2 == 0 else task_b
        focus = service.create_session(plan.id, task.id, {})
        finish_planned(service, focus)
        state = service.get_pomodoro_state(plan.id)
        if index < 3:
            assert state["next_session_type"] == StudySessionType.SHORT_BREAK.value
            break_session = service.create_session(plan.id, task.id, {})
            assert break_session.session_type is StudySessionType.SHORT_BREAK
            assert break_session.planned_minutes == 5
            finish_planned(service, break_session)
        else:
            assert state["next_session_type"] == StudySessionType.LONG_BREAK.value
            assert state["next_minutes"] == 15
            assert state["focuses_in_cycle"] == 4
    long_break = service.create_session(plan.id, task_b.id, {})
    assert long_break.session_type is StudySessionType.LONG_BREAK
    assert long_break.planned_minutes == 15
    finish_planned(service, long_break)
    state = service.get_pomodoro_state(plan.id)
    assert state["focuses_in_cycle"] == 0
    assert state["next_session_type"] == StudySessionType.FOCUS.value
    assert state["next_minutes"] == 25


def test_plan_allows_only_one_active_pomodoro_session(tmp_path):
    service, plan, task_a, task_b = make_service(tmp_path)
    first = service.create_session(plan.id, task_a.id, {})
    assert first.status is StudySessionStatus.PLANNED
    with pytest.raises(ValueError, match="already active"):
        service.create_session(plan.id, task_b.id, {})


def test_backend_rejects_skipping_required_break(tmp_path):
    service, plan, task_a, _ = make_service(tmp_path)
    focus = service.create_session(plan.id, task_a.id, {})
    finish_planned(service, focus)
    with pytest.raises(ValueError, match="short_break"):
        service.create_session(plan.id, task_a.id, {"session_type": StudySessionType.FOCUS.value})
