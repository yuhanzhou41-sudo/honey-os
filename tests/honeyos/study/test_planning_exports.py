import asyncio
from datetime import date
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from honeyos.gateway.config import PlatformConfig
from honeyos.gateway.platforms.api_server import APIServerAdapter
from honeyos.study.markdown import StudyPlanMarkdownError, parse_study_plan_markdown
from honeyos.study.models import StudyPlan
from honeyos.study.planning import (
    authoring_guide, build_planning_request, planning_capabilities,
    planning_instructions, template_markdown,
)
from honeyos.study.planning_http import planning_routes
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService


@pytest.fixture
def study(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    return StudyService(StudyRepository(tmp_path))


@pytest.mark.parametrize("version", [1, 2])
def test_versioned_templates_have_no_runtime_ids_and_import(study, version):
    raw = template_markdown(version)
    assert raw.startswith("---\n")
    assert "id:" not in raw and "```" not in raw
    preview = study.preview_markdown_plan(raw)
    assert preview.schema_version == version
    assert not study.list_plans()
    saved = study.import_markdown_plan(raw)
    assert saved.schema_version == version
    if version == 2:
        assert saved.tasks[0].minimum_required
        assert saved.flex_slots


def test_request_limits_selected_materials_and_replaces_plan_capacity(study):
    original = study.repository.save_new_plan(StudyPlan(
        title="Existing", start_date=date(2026, 11, 19), end_date=date(2026, 11, 20),
        status="active", tasks=[{
            "title": "Original", "scheduled_date": "2026-11-19", "planned_minutes": 30,
        }],
    ))
    study.set_daily_capacity("2026-11-19", 120)
    attachment = study.attachments.upload_bytes(
        ("selected " * 500).encode(), original_filename="selected.txt",
        declared_mime_type="text/plain", source_type="study",
    )
    selected = study.create_resource({
        "title": "Selected notes", "resource_type": "document", "attachment_id": attachment.id,
    })
    unselected = study.create_resource({
        "title": "Private unselected", "resource_type": "document", "attachment_id": attachment.id,
    })
    raw = build_planning_request(study, {
        "objective": "Exam", "start_date": "2026-11-19", "end_date": "2026-11-20",
        "resource_ids": [selected.id], "plan_id": original.id,
    })
    assert "Selected notes" in raw and unselected.title not in raw
    assert '"other_minutes": 0' in raw
    assert '"limit_minutes": 120' in raw and '"truncated": true' in raw
    assert "captured_at" in raw and original.id in raw
    assert len(study.list_plans()) == 1
    with pytest.raises(StudyPlanMarkdownError):
        parse_study_plan_markdown(raw)


def test_internal_skill_uses_current_runtime_and_real_capacity(study):
    study.set_daily_capacity("2026-11-19", 75)
    with patch("honeyos.study.planning.datetime") as clock:
        from datetime import datetime, timezone
        clock.now.return_value = datetime(2026, 11, 19, tzinfo=timezone.utc)
        raw = planning_instructions()
    assert authoring_guide() in raw
    assert '"limit_minutes": 75' in raw and "flex_slots" in raw
    assert "study_plan_version: 1" not in raw
    assert not study.list_plans()


@pytest.mark.parametrize("payload", [
    {"objective": "", "start_date": "2026-11-19", "end_date": "2026-11-20"},
    {"objective": "Exam", "start_date": "2026-11-20", "end_date": "2026-11-19"},
    {"objective": "Exam", "start_date": "2026-11-19", "end_date": "2026-11-20", "sunlight": 5},
])
def test_invalid_requests_rejected_without_plans(study, payload):
    with pytest.raises(ValueError):
        build_planning_request(study, payload)
    assert study.list_plans() == []


def test_runtime_download_preview_import_and_request_http(study):
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
            headers = {"Authorization": "Bearer " + "a" * 32}
            response = await client.get("/api/study/planning/capabilities", headers=headers)
            assert await response.json() == planning_capabilities()
            response = await client.get("/api/study/plans/template?version=3", headers=headers)
            assert response.status == 400
            for version in (1, 2):
                response = await client.get(f"/api/study/plans/template?version={version}", headers=headers)
                raw = await response.text()
                assert parse_study_plan_markdown(raw).schema_version == version
                response = await client.post("/preview", json={"markdown": raw}, headers=headers)
                assert response.status == 200
                response = await client.post("/import", json={"markdown": raw}, headers=headers)
                assert response.status == 201
                assert (await response.json())["plan"]["schema_version"] == version
            response = await client.get("/api/study/plans/template", headers=headers)
            assert parse_study_plan_markdown(await response.text()).schema_version == 2
            response = await client.post("/api/study/planning/request", json={
                "objective": "Revision", "start_date": "2026-11-19", "end_date": "2026-11-20",
            })
            assert response.status == 401
            response = await client.post("/api/study/planning/request", json={
                "objective": "Revision", "start_date": "2026-11-19", "end_date": "2026-11-20",
            }, headers=headers)
            assert response.status == 200
            assert "planning_request.md" in response.headers["Content-Disposition"]
            request = await response.text()
            assert request.startswith("# Planning Request") and "study_plan.md" in request
            assert len(study.list_plans()) == 2

    asyncio.run(scenario())



def test_manual_preview_is_read_only_and_rejects_stale_confirmation(study):
    saved = study.import_markdown_plan(template_markdown())
    before, proposed = study.preview_update(saved.id, {"title": "Proposed"})
    assert proposed.title == "Proposed"
    assert study.get_plan(saved.id).title == saved.title
    study.update_task(saved.id, saved.tasks[0].id, {"description": "Concurrent edit"})
    with pytest.raises(ValueError, match="计划已变化"):
        study.confirm_update(saved.id, {"title": "Proposed"}, expected_updated_at=before.updated_at.isoformat())
    assert study.get_plan(saved.id).title == saved.title
    current = study.get_plan(saved.id)
    changed = study.confirm_update(saved.id, {"title": "Confirmed"}, expected_updated_at=current.updated_at.isoformat())
    assert changed.title == "Confirmed"
