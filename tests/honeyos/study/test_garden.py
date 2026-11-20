from datetime import datetime, timezone
import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from honeyos.study.garden import StudyGarden
from honeyos.study.models import StudyPlan
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService


@pytest.fixture
def garden(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    study = StudyService(StudyRepository(tmp_path))
    monkeypatch.setattr(study, "_now", lambda: datetime(2026, 11, 20, 10, tzinfo=timezone.utc))
    return StudyGarden(study)


def make(garden):
    return garden.study.repository.save_new_plan(StudyPlan(
        schema_version=2, title="My plant", status="active", start_date="2026-11-19", end_date="2026-12-05",
        tasks=[{"title": "Real task", "scheduled_date": "2026-11-20", "planned_minutes":20},
               {"title": "Future task", "scheduled_date": "2026-12-01", "planned_minutes":20}]))


def test_live_plant_rebuilds_from_task_changes_without_duplicate_plants(garden):
    plan = make(garden)
    assert garden.listing()["plants"] == []
    garden.memory.growth.enable(plan.id, {})
    first = garden.listing()["plants"][0]
    assert first["tasks"] == 2 and first["completed"] == 0 and not first["planted"]
    garden.study.set_task_status(plan.id, plan.tasks[0].id, "completed")
    second = garden.listing()["plants"][0]
    assert second["completed"] == 1
    assert garden.summary(plan.id, "month", "2026-11-20")["stats"]["completed"] == 1
    assert len(StudyGarden(garden.study).listing()["plants"]) == 1


def test_closed_plant_retains_calendar_facts_after_weekly_cleanup_and_plan_deletion(garden):
    plan = make(garden)
    garden.study.set_task_status(plan.id, plan.tasks[0].id, "completed")
    garden.memory.weekly(plan.id, "2026-11-20")
    proposal = garden.memory.close_preview(plan.id, "completed")
    garden.memory.close(plan.id, "completed", proposal["expected_updated_at"], proposal["facts_revision"])
    card = garden.listing()["plants"][0]
    assert card["planted"] and card["closed"] and card["summary"]
    for period in ("week", "month", "year"):
        result = garden.summary(plan.id, period, "2026-11-20")
        assert result["archived"] and result["stats"]["completed"] == 1
    with garden.study.repository._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM study_weekly_reports").fetchone()[0] == 0
    garden.study.delete_plan(plan.id)
    restored = StudyGarden(garden.study)
    assert restored.listing()["plants"][0]["planted"]
    assert restored.summary(plan.id, "year", "2026-11-20")["stats"]["completed"] == 1


def test_stopped_plan_keeps_plant_without_claiming_completed(garden):
    plan = make(garden)
    proposal = garden.memory.close_preview(plan.id, "stopped")
    garden.memory.close(plan.id, "stopped", proposal["expected_updated_at"], proposal["facts_revision"])
    card = garden.listing()["plants"][0]
    assert card["closed"] and not card["planted"]
    assert "主动停止" in card["summary"]


def test_calendar_periods_empty_future_and_invalid_inputs(garden):
    plan = make(garden)
    garden.memory.growth.enable(plan.id, {})
    leap = garden.summary(plan.id, "month", "2024-02-18")
    assert leap["start_date"] == "2024-02-01" and leap["end_date"] == "2024-02-29"
    assert leap["stats"]["completion_rate"] is None
    week = garden.summary(plan.id, "week", "2027-01-01")
    assert week["start_date"] == "2026-12-28" and week["end_date"] == "2027-01-03"
    assert week["days"] == []
    assert garden.summary(plan.id, "year", "2026-01-01")["stats"]["tasks"] == 1
    with pytest.raises(ValueError): garden.summary(plan.id, "decade", "2026-11-20")
    with pytest.raises(KeyError): garden.summary("absent", "week", "2026-11-20")


def test_garden_http_auth_calendar_and_profile_isolation(garden, tmp_path):
    from honeyos.gateway.config import PlatformConfig
    from honeyos.gateway.platforms.api_server import APIServerAdapter
    from honeyos.study.growth_http import growth_routes
    plan = make(garden)
    garden.memory.growth.enable(plan.id, {})
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key":"a"*32}))
    async def scenario():
        app = web.Application()
        for method, path, handler in growth_routes(adapter): app.router.add_route(method, path, handler)
        async with TestClient(TestServer(app)) as client:
            assert (await client.get("/api/study/growth/garden")).status == 401
            headers={"Authorization":"Bearer "+"a"*32}
            result=await client.get("/api/study/growth/garden",headers=headers)
            assert (await result.json())["plants"][0]["plan_id"] == plan.id
            result=await client.get("/api/study/growth/garden-summary",params={"plan_id":plan.id,"period":"month","date":"2026-11-20"},headers=headers)
            assert result.status == 200 and (await result.json())["period"] == "month"
    asyncio.run(scenario())
    assert StudyGarden(StudyService(StudyRepository(tmp_path/"other-profile"))).listing()["plants"] == []


def test_late_live_projection_cannot_overwrite_closed_plant(garden):
    plan = make(garden)
    garden.memory.growth.enable(plan.id, {})
    stale = garden.prepare(plan.id)
    proposal = garden.memory.close_preview(plan.id, "completed")
    garden.memory.close(plan.id, "completed", proposal["expected_updated_at"], proposal["facts_revision"])
    garden.save(stale)
    assert garden.listing()["plants"][0]["planted"]
