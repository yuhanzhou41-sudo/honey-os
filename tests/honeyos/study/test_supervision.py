import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from honeyos.study.models import StudyPlan
from honeyos.study.service import StudyService
from honeyos.study.repository import StudyRepository
from honeyos.study.supervision import StudySupervision


@pytest.fixture
def store(tmp_path,monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME",str(tmp_path))
    study=StudyService(StudyRepository(tmp_path))
    now=datetime(2026,11,20,11,tzinfo=timezone.utc)
    monkeypatch.setattr(study,"_now",lambda:now)
    store=StudySupervision(study)
    for name in ("A","B"):
        plan=study.repository.save_new_plan(StudyPlan(
            title=name,status="active",start_date="2026-11-20",end_date="2026-11-22",
            tasks=[{"title":"Task","scheduled_date":"2026-11-20","planned_minutes":25}],
        ))
        store.memory.growth.enable(plan.id,{"timezone":"Asia/Shanghai"})
    return store


def test_defaults_quiet_hours_and_running_timer(store):
    now=store.study._now()
    assert store.facts(now) is None
    store.configure({"enabled":True,"session_id":"chat"})
    facts=store.facts(now)
    assert facts["tasks"]==2 and len(facts["plan_ids"])==2
    assert store.facts(now.replace(hour=15)) is None
    plan=store.study.list_plans()[0]
    session=store.study.create_session(plan.id,plan.tasks[0].id,{"planned_minutes":25})
    with store.study.repository._connect() as db:
        db.execute("UPDATE study_sessions SET status='running' WHERE id=?",(session.id,))
    assert store.facts(now) is None


def test_delivery_failure_retries_same_key_then_daily_limit(store,monkeypatch):
    store.configure({"enabled":True,"session_id":"chat"})
    monkeypatch.setattr(store,"message",lambda facts:"先选最重要的内容开始。")
    calls=[]
    class Adapter:
        async def send(self,session_id,message,metadata):
            calls.append(metadata["delivery_id"])
            return SimpleNamespace(success=len(calls)>1)
    async def scenario():
        adapter=Adapter()
        assert not await store.deliver(adapter,store.study._now())
        assert await store.deliver(adapter,store.study._now())
        assert not await store.deliver(adapter,store.study._now())
    asyncio.run(scenario())
    assert len(calls)==2 and len(set(calls))==1


@pytest.mark.parametrize("completed",range(25))
def test_qwen_cannot_invent_numbers(store,monkeypatch,completed):
    monkeypatch.setattr("honeyos.study.local_model._generate",lambda *a,**k:
        json.dumps({"kind":"pending","advice":"先完成999道题。"}))
    message=store.message({"kind":"pending","tasks":25,"completed":completed,"focus_minutes":0})
    assert "999" not in message
    assert f"{completed}/25" in message
    assert len(message)<=80


def test_consent_withdrawn_during_model_call_prevents_delivery(store,monkeypatch):
    store.configure({"enabled":True,"session_id":"chat"})
    def withdraw(facts):
        store.configure({"enabled":False})
        return "先休息。"
    monkeypatch.setattr(store,"message",withdraw)
    class Adapter:
        async def send(self,*a,**k):
            raise AssertionError("must not send")
    assert not asyncio.run(store.deliver(Adapter(),store.study._now()))


def test_proactive_delivery_id_is_atomic_in_existing_message_store(tmp_path):
    from honeyos.core.state import SessionDB
    from concurrent.futures import ThreadPoolExecutor
    db=SessionDB(tmp_path/"state.db")
    db.create_session("session","api_server")
    def append(_):
        return db.append_message("session","assistant","Study message",display_kind="proactive",
                                 display_metadata={"delivery_id":"study:unique-day"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(append,range(2)))
    assert ids[0]==ids[1]
    assert len(db.get_messages("session"))==1
    db.close()
