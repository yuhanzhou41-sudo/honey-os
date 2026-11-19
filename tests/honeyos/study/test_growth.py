from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest

from honeyos.study.growth import StudyGrowth, day_level
from honeyos.study.models import StudyPlan, StudyTaskStatus
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService
from honeyos.study.review import StudyReview
from honeyos.study.activity import assign_event

@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    study = StudyService(StudyRepository(tmp_path))
    return study, StudyGrowth(study)

def make_plan(study):
    return study.repository.save_new_plan(StudyPlan(
        schema_version=2, title="Growth", start_date="2026-11-19", end_date="2026-11-25",
        tasks=[{"title":"Minimum", "scheduled_date":"2026-11-19", "planned_minutes":15,
                "priority":"must", "minimum_required":True},
               {"title":"Standard", "scheduled_date":"2026-11-19", "planned_minutes":15}],
        flex_slots=[{"scheduled_date":"2026-11-20","planned_minutes":30}],
    ))

def test_levels_empty_and_minimum(app):
    study, growth = app
    plan=make_plan(study)
    assert day_level([]) == "no_tasks"
    plan.tasks[0].status=StudyTaskStatus.COMPLETED
    from honeyos.study.validation import validate_study_plan
    plan=validate_study_plan(plan)
    assert day_level(plan.tasks,True) == "minimum"
    assert day_level(plan.tasks,False) == "incomplete"
    plan.tasks[1].status=StudyTaskStatus.COMPLETED
    assert day_level(validate_study_plan(plan).tasks) == "full"

def test_flex_use_retry_undo_and_cas(app):
    study,growth=app
    plan=make_plan(study)
    task,slot=plan.tasks[0],plan.flex_slots[0]
    before,preview=growth.flex_preview(plan.id,task.id,slot.id)
    assert study.get_plan(plan.id).tasks[0].scheduled_date == task.scheduled_date
    used=growth.use_flex(plan.id,task.id,slot.id,"request",plan.updated_at.isoformat())
    assert used.flex_slots[0].planned_minutes == 15
    assert growth.use_flex(plan.id,task.id,slot.id,"request","old").id == plan.id
    restored=growth.undo_flex(plan.id,"request",used.updated_at.isoformat())
    assert restored.flex_slots[0].planned_minutes == 30
    assert next(t for t in restored.tasks if t.id==task.id).scheduled_date == task.scheduled_date
    assert growth.undo_flex(plan.id,"request","old").id == plan.id

def test_rewards_no_backfill_retry_and_reversal(app,monkeypatch):
    study,growth=app
    now=datetime(2026,11,19,10,tzinfo=timezone.utc)
    monkeypatch.setattr(study,"_now",lambda:now)
    plan=make_plan(study)
    growth.enable(plan.id,{"timezone":"Asia/Shanghai"})
    now+=timedelta(seconds=1)
    for task in plan.tasks:
        study.set_task_status(plan.id,task.id,"completed")
    first=growth.state(plan.id)
    assert first["sunlight"] in (10,20,30)
    assert growth.state(plan.id)["sunlight"] == first["sunlight"]
    study.set_task_status(plan.id,plan.tasks[0].id,"planned")
    assert growth.state(plan.id)["sunlight"] == 0
    assert growth.state(plan.id)["plant"] == first["plant"]

def test_recovery_preview_is_small_and_readonly(app):
    study,growth=app
    plan=make_plan(study)
    proposal=growth.recovery(plan.id,"2026-11-20")
    assert len(proposal["task_ids"])<=3
    assert study.get_plan(plan.id).updated_at == plan.updated_at

def test_attribution_owns_one_event_and_retry_is_stable(app):
    study,growth=app
    first,second=make_plan(study),make_plan(study)
    review=StudyReview(study)
    with study.repository._connect() as db:
        db.execute("INSERT INTO study_review_questions VALUES (?,?,?,?,?,?,?,?)",
                   ("question","Prompt",'["A","B"]',0,"why","","source","quote"))
    review.attempt("question",0,"attempt",first.id)
    review.attempt("question",0,"attempt",first.id)
    with pytest.raises(ValueError):
        review.attempt("question",0,"attempt",second.id)
    assign_event(study,"attempt","attempt",second.id)
    with study.repository._connect() as db:
        row=db.execute("SELECT plan_id FROM study_activity_attribution WHERE event_id='attempt'").fetchone()
        assert row["plan_id"]==second.id
        assert db.execute("SELECT COUNT(*) FROM study_review_attempts").fetchone()[0]==1



def test_editing_old_completed_task_does_not_backfill_rewards(app,monkeypatch):
    study,growth=app
    clock=datetime(2026,11,19,10,tzinfo=timezone.utc)
    monkeypatch.setattr(study,"_now",lambda:clock)
    plan=make_plan(study)
    for task in plan.tasks:
        study.set_task_status(plan.id,task.id,"completed")
    clock+=timedelta(seconds=2)
    growth.enable(plan.id,{"timezone":"Asia/Shanghai"})
    study.update_task(plan.id,plan.tasks[0].id,{"description":"Metadata change"})
    assert growth.state(plan.id)["sunlight"]==0


def test_pruned_review_keeps_single_archived_learning_fact(app):
    study,growth=app
    plan=make_plan(study)
    review=StudyReview(study)
    with study.repository._connect() as db:
        db.execute("INSERT INTO study_review_questions VALUES (?,?,?,?,?,?,?,?)",
                   ("q_arch","Prompt",'["A","B"]',0,"why","resource_arch","source","quote"))
    review.attempt("q_arch",0,"attempt_arch",plan.id)
    review.prune_derivatives(["resource_arch"])
    with study.repository._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM study_review_attempts WHERE id='attempt_arch'").fetchone()[0]==0
        assert db.execute("SELECT COUNT(*) FROM study_learning_attempts WHERE id='attempt_arch'").fetchone()[0]==1
        assert db.execute("SELECT plan_id FROM study_activity_attribution WHERE event_id='attempt_arch'").fetchone()[0]==plan.id
