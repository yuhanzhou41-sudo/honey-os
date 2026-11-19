from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from honeyos.study.models import StudyPlan, StudyPlanStatus
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService

DAY = "2026-11-19"


def plan(minutes, flex=0):
    return StudyPlan.model_validate({
        "schema_version": 2, "title": "Capacity", "status": "active",
        "start_date": DAY, "end_date": DAY,
        "tasks": [{"title": "Practice", "scheduled_date": DAY, "planned_minutes": minutes}],
        "flex_slots": [{"scheduled_date": DAY, "planned_minutes": flex}] if flex else [],
    })


@pytest.fixture
def study(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    return StudyService(StudyRepository(tmp_path))


def test_unknown_capacity_and_replacement_candidate(study):
    first = study.repository.save_new_plan(plan(60, 10))
    study.repository.save_new_plan(plan(30, 5))
    [day] = study.plan_capacity(first)
    assert day["total_minutes"] == 105
    assert day["limit_minutes"] is None and not day["verified"]
    first.tasks[0].planned_minutes = 20
    [day] = study.plan_capacity(first)
    assert day["candidate_minutes"] == 30
    assert day["other_minutes"] == 35
    assert day["total_minutes"] == 65


def test_known_limit_and_failed_update_are_atomic(study):
    first = study.repository.save_new_plan(plan(30))
    second = study.repository.save_new_plan(plan(20))
    study.set_daily_capacity(DAY, 50)
    with pytest.raises(ValueError, match="超过"):
        study.update_task(second.id, second.tasks[0].id, {"planned_minutes": 21})
    assert study.get_plan(second.id).tasks[0].planned_minutes == 20
    assert study.get_plan(first.id).tasks[0].planned_minutes == 30
    with pytest.raises(ValueError, match="超过"):
        study.repository.save_new_plan(plan(1, 1))
    assert len(study.list_plans()) == 2


def test_lower_limit_allows_completion_and_reduction(study):
    saved = study.repository.save_new_plan(plan(60))
    study.set_daily_capacity(DAY, 30)
    changed = study.set_task_status(saved.id, saved.tasks[0].id, "completed")
    assert changed.tasks[0].status.value == "completed"
    changed = study.update_task(saved.id, saved.tasks[0].id, {"planned_minutes": 40})
    assert changed.tasks[0].planned_minutes == 40
    changed = study.update_plan(saved.id, {"status": "archived"})
    assert changed.status.value == "archived"


def test_stale_capacity_snapshot_cannot_bypass_limit(study):
    proposed = plan(60)
    assert not study.plan_capacity(proposed)[0]["verified"]
    study.set_daily_capacity(DAY, 30)
    with pytest.raises(ValueError, match="超过"):
        study.repository.save_new_plan(proposed)
    assert study.list_plans() == []


def test_paused_plans_do_not_use_other_plan_capacity(study):
    paused = plan(90, 30)
    paused.status = StudyPlanStatus.PAUSED
    study.repository.save_new_plan(paused)
    study.set_daily_capacity(DAY, 60)
    saved = study.repository.save_new_plan(plan(60))
    assert study.plan_capacity(saved)[0]["other_minutes"] == 0
    with pytest.raises(ValueError, match="超过"):
        study.update_plan(paused.id, {"status": "active"})


def test_concurrent_saves_cannot_overbook(study):
    study.set_daily_capacity(DAY, 60)
    barrier = Barrier(2)

    def save_one(_):
        candidate = plan(40)
        barrier.wait(timeout=5)
        try:
            study.repository.save_new_plan(candidate)
            return "saved"
        except ValueError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save_one, range(2))) == ["rejected", "saved"]
    assert len(study.list_plans()) == 1


@pytest.mark.parametrize("minutes", [-1, 1441, 1.5, True, "60"])
def test_invalid_limits_rejected(study, minutes):
    with pytest.raises(ValueError):
        study.set_daily_capacity(DAY, minutes)


def test_zero_limit_and_clear(study):
    study.set_daily_capacity(DAY, 0)
    assert study.plan_capacity(plan(1))[0]["overloaded"]
    study.set_daily_capacity(DAY, None)
    assert not study.plan_capacity(plan(1))[0]["verified"]



def test_default_repository_respects_profile_capacity_isolation(tmp_path):
    from honeyos.core.constants import set_honeyos_home_override, reset_honeyos_home_override

    token = set_honeyos_home_override(tmp_path / "first")
    try:
        first = StudyService()
        first.set_daily_capacity(DAY, 30)
    finally:
        reset_honeyos_home_override(token)
    token = set_honeyos_home_override(tmp_path / "second")
    try:
        second = StudyService()
        assert not second.plan_capacity(plan(60))[0]["verified"]
        assert second.list_plans() == []
    finally:
        reset_honeyos_home_override(token)
    assert first.plan_capacity(plan(60))[0]["limit_minutes"] == 30



def test_authenticated_capacity_and_markdown_http(study):
    import asyncio
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from honeyos.gateway.config import PlatformConfig
    from honeyos.gateway.platforms.api_server import APIServerAdapter
    from honeyos.study.planning_http import planning_routes
    from honeyos.study.markdown import export_study_plan_markdown

    study.repository.save_new_plan(plan(30))
    candidate = plan(40)
    candidate.status = StudyPlanStatus.DRAFT
    markdown = export_study_plan_markdown(candidate)
    adapter = APIServerAdapter(PlatformConfig(
        enabled=True, extra={"host": "127.0.0.1", "port": 8642, "key": "a" * 32},
    ))

    async def scenario():
        app = web.Application()
        for method, path, handler in planning_routes(adapter):
            app.router.add_route(method, path, handler)
        app.router.add_post("/preview", adapter._authenticated_file_handler(
            adapter._handle_study_preview_markdown_import))
        app.router.add_post("/import", adapter._authenticated_file_handler(
            adapter._handle_study_import_markdown_plan))
        async with TestClient(TestServer(app)) as client:
            response = await client.put("/api/study/capacity/" + DAY, json={"minutes": 60})
            assert response.status == 401
            headers = {"Authorization": "Bearer " + "a" * 32}
            response = await client.put("/api/study/capacity/" + DAY, json={"minutes": 60}, headers=headers)
            assert response.status == 200
            response = await client.post("/preview", json={"markdown": markdown}, headers=headers)
            assert response.status == 200
            payload = await response.json()
            assert payload["capacity"][0]["total_minutes"] == 70
            assert payload["capacity"][0]["overloaded"]
            response = await client.post("/import", json={"markdown": markdown}, headers=headers)
            assert response.status == 400
            assert len(study.list_plans()) == 1
            response = await client.put("/api/study/capacity/" + DAY, json={"minutes": None}, headers=headers)
            assert response.status == 200
            response = await client.post("/import", json={"markdown": markdown}, headers=headers)
            assert response.status == 201

    asyncio.run(scenario())
