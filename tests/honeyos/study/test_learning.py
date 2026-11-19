from datetime import datetime, timedelta, timezone
import json
import pytest

from honeyos.study.learning import StudyLearningMemory
from honeyos.study.service import StudyService
from honeyos.study.repository import StudyRepository
from honeyos.study.models import StudyPlan

@pytest.fixture
def memory(tmp_path,monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME",str(tmp_path))
    study=StudyService(StudyRepository(tmp_path))
    monkeypatch.setattr(study,"_now",lambda:datetime(2026,11,20,15,tzinfo=timezone.utc))
    return StudyLearningMemory(study)

def make_plan(memory):
    return memory.study.repository.save_new_plan(StudyPlan(
        title="Memory", start_date="2026-11-19",end_date="2026-11-25",
        tasks=[{"title":"Task","scheduled_date":"2026-11-20","planned_minutes":25}],
    ))

def test_snapshot_rebuilds_late_data_and_context_boundary(memory):
    plan=make_plan(memory)
    assert memory.context(plan.id,"2026-11-20") is None
    first=memory.snapshot(plan.id,"2026-11-20")
    assert first["completed"]==0
    memory.study.set_task_status(plan.id,plan.tasks[0].id,"completed")
    assert memory.snapshot(plan.id,"2026-11-20")["completed"]==1
    assert memory.context(plan.id,"2026-11-20",explicit_question=True)["source"]
    with memory.study.repository._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM study_daily_memory").fetchone()[0]==1

def test_closing_one_plan_keeps_other_history_and_is_idempotent(memory):
    first,second=make_plan(memory),make_plan(memory)
    memory.weekly(first.id,"2026-11-17")
    memory.weekly(second.id,"2026-11-17")
    proposal=memory.close_preview(first.id,"stopped")
    closed=memory.close(first.id,"stopped",proposal["expected_updated_at"],proposal["facts_revision"])
    assert closed["summary"].count("。")==1
    assert memory.close(first.id,"stopped","old","old")==closed
    with memory.study.repository._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM study_weekly_reports WHERE plan_id=?",(first.id,)).fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM study_weekly_reports WHERE plan_id=?",(second.id,)).fetchone()[0]==1
        assert db.execute("SELECT COUNT(*) FROM study_daily_memory WHERE plan_id=?",(first.id,)).fetchone()[0]>0
    assert len(memory.study.get_plan(first.id).tasks)==1
    assert memory.weekly(first.id,"2026-11-17")["archived"]
    with pytest.raises(ValueError):
        memory.study.update_task(first.id,first.tasks[0].id,{"title":"Overwrite"})

def test_close_refuses_stale_learning_facts(memory):
    plan=make_plan(memory)
    proposal=memory.close_preview(plan.id,"completed")
    memory.study.set_task_status(plan.id,plan.tasks[0].id,"completed")
    with pytest.raises(ValueError):
        memory.close(plan.id,"completed",proposal["expected_updated_at"],proposal["facts_revision"])
    assert memory.closure(plan.id) is None

def test_empty_day_is_not_completed(memory):
    plan=make_plan(memory)
    assert memory.snapshot(plan.id,"2026-11-21")["level"]=="no_tasks"
    assert memory.snapshot(plan.id,"2026-11-21")["focus_minutes"]==0



def test_maintenance_rebuilds_dirty_past_date_after_restart(memory,monkeypatch):
    plan=make_plan(memory)
    clock=datetime(2026,11,20,11,tzinfo=timezone.utc)
    monkeypatch.setattr(memory.study,"_now",lambda:clock)
    memory.growth.enable(plan.id,{"timezone":"Asia/Shanghai"})
    memory.maintain()
    clock+=timedelta(days=2)
    memory.maintain()
    memory.study.set_task_status(plan.id,plan.tasks[0].id,"completed")
    memory.maintain()
    with memory.study.repository._connect() as db:
        stored=db.execute("SELECT snapshot_json FROM study_daily_memory WHERE plan_id=? AND local_date='2026-11-20'",(plan.id,)).fetchone()
        assert json.loads(stored[0])["completed"]==1


def test_version_advances_even_when_clock_does_not(memory):
    plan=make_plan(memory)
    before,preview=memory.study.preview_update(plan.id,{"title":"First"})
    first=memory.study.confirm_update(plan.id,{"title":"First"},expected_updated_at=before.updated_at.isoformat())
    assert first.updated_at>before.updated_at
    with pytest.raises(ValueError):
        memory.study.confirm_update(plan.id,{"title":"Stale"},expected_updated_at=before.updated_at.isoformat())



def test_focus_allocation_across_dst_midnight_preserves_total(memory):
    from honeyos.study.models import StudySession
    plan=memory.study.repository.save_new_plan(StudyPlan(
        title="DST",start_date="2026-10-31",end_date="2026-11-02",
        tasks=[{"title":"Focus","scheduled_date":"2026-10-31"}],
    ))
    memory.study.sessions.save_session(StudySession(
        task_id=plan.tasks[0].id,status="completed",session_type="focus",planned_minutes=120,actual_minutes=120,
        started_at=datetime(2026,11,1,3,tzinfo=timezone.utc),
        ended_at=datetime(2026,11,1,7,tzinfo=timezone.utc),
    ))
    first=memory.growth.facts(plan.id,"2026-10-31","America/New_York")
    second=memory.growth.facts(plan.id,"2026-11-01","America/New_York")
    assert first["focus_minutes"]+second["focus_minutes"]==120
    assert set(first["sources"]["focus"])==set(second["sources"]["focus"])



def test_existing_status_api_also_finishes_with_final_summary(memory):
    plan=make_plan(memory)
    memory.weekly(plan.id,"2026-11-17")
    saved=memory.study.update_plan(plan.id,{"status":"completed"})
    assert saved.status.value=="completed"
    assert memory.closure(plan.id)["reason"]=="completed"
    assert memory.study.update_plan(plan.id,{"status":"completed"}).id==plan.id
    with memory.study.repository._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM study_weekly_reports WHERE plan_id=?",(plan.id,)).fetchone()[0]==0



def test_close_cleanup_failure_rolls_back_final_and_status(memory):
    import sqlite3
    plan=make_plan(memory)
    memory.weekly(plan.id,"2026-11-17")
    proposal=memory.close_preview(plan.id,"stopped")
    with memory.study.repository._connect() as db:
        db.execute("CREATE TRIGGER fail_cleanup BEFORE DELETE ON study_weekly_reports BEGIN SELECT RAISE(ABORT,'test rollback'); END")
    with pytest.raises(sqlite3.IntegrityError):
        memory.close(plan.id,"stopped",proposal["expected_updated_at"],proposal["facts_revision"])
    assert memory.closure(plan.id) is None
    assert memory.study.get_plan(plan.id).status.value=="draft"
    with memory.study.repository._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM study_weekly_reports WHERE plan_id=?",(plan.id,)).fetchone()[0]==1
        db.execute("DROP TRIGGER fail_cleanup")
    assert memory.close(plan.id,"stopped",proposal["expected_updated_at"],proposal["facts_revision"])["reason"]=="stopped"
