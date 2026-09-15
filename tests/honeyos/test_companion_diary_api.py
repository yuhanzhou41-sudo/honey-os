from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from honeyos.gateway.config import PlatformConfig
from honeyos.gateway.platforms.api_server import APIServerAdapter


def _adapter() -> APIServerAdapter:
    return APIServerAdapter(
        PlatformConfig(
            enabled=True,
            extra={"host": "127.0.0.1", "port": 8642, "key": "a" * 32},
        )
    )


def _request(adapter, *, payload=None, entry_id=""):
    request = SimpleNamespace(
        cookies={"honeyos_local": adapter._local_web_token},
        remote="127.0.0.1",
        headers={},
        app={},
        match_info={"entry_id": entry_id},
    )
    if payload is not None:
        request.json = AsyncMock(return_value=payload)
    return request


def test_api_server_registers_diary_routes():
    adapter = _adapter()
    routes = {(method, path) for method, path, _ in adapter._http_route_table()}

    assert ("GET", "/diary") in routes
    assert ("GET", "/api/companion/diary") in routes
    assert ("POST", "/api/companion/diary") in routes
    assert ("POST", "/api/companion/diary/retry") in routes
    assert ("PATCH", "/api/companion/diary/{entry_id}") in routes
    assert ("DELETE", "/api/companion/diary/{entry_id}") in routes


@pytest.mark.asyncio
async def test_companion_diary_user_crud(monkeypatch, tmp_path):
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    adapter = _adapter()

    create_response = await adapter._handle_companion_diary_create(
        _request(
            adapter,
            payload={"entry_date": "2026-09-15", "content": "今天开始写日记。"},
        )
    )
    created = json.loads(create_response.text)["entry"]
    assert create_response.status == 201
    assert created["author"] == "user"
    assert created["allow_ai_view"] is True
    assert created["allow_memory"] is False

    list_response = await adapter._handle_companion_diary(_request(adapter))
    assert json.loads(list_response.text)["entries"] == [created]

    update_response = await adapter._handle_companion_diary_update(
        _request(adapter, payload={"content": "修改后的日记。"}, entry_id=created["id"])
    )
    updated = json.loads(update_response.text)["entry"]
    assert updated["content"] == "修改后的日记。"

    permission_response = await adapter._handle_companion_diary_update(
        _request(
            adapter,
            payload={"allow_memory": True},
            entry_id=created["id"],
        )
    )
    permitted = json.loads(permission_response.text)["entry"]
    assert permitted["allow_ai_view"] is True
    assert permitted["allow_memory"] is True

    delete_response = await adapter._handle_companion_diary_delete(
        _request(adapter, entry_id=created["id"])
    )
    assert json.loads(delete_response.text) == {"success": True, "id": created["id"]}

    empty_response = await adapter._handle_companion_diary(_request(adapter))
    assert json.loads(empty_response.text)["entries"] == []


@pytest.mark.asyncio
async def test_companion_diary_rejects_invalid_content(monkeypatch, tmp_path):
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    adapter = _adapter()

    response = await adapter._handle_companion_diary_create(
        _request(adapter, payload={"entry_date": "2026-09-15", "content": "   "})
    )

    assert response.status == 400
    assert json.loads(response.text) == {"error": "diary_content_required"}


@pytest.mark.asyncio
async def test_companion_diary_cannot_change_assistant_entry(monkeypatch, tmp_path):
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    from honeyos.companion.diary import DiaryStore

    assistant = DiaryStore(tmp_path).create_entry(
        author="assistant", entry_date="2026-09-15", content="AI 的日记"
    )
    adapter = _adapter()
    response = await adapter._handle_companion_diary_update(
        _request(adapter, payload={"content": "不能覆盖"}, entry_id=assistant.id)
    )

    assert response.status == 404
    assert DiaryStore(tmp_path).list_entries()[0].content == "AI 的日记"
