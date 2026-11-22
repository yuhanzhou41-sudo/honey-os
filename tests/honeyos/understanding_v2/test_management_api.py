import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from honeyos.gateway.config import PlatformConfig
from honeyos.gateway.platforms.api_server import APIServerAdapter
from honeyos.understanding.u2_contracts import Proposal
from honeyos.understanding.u2_maintenance import apply_proposal
from honeyos.understanding.u2_store import UnderstandingStore


def adapter():
    return APIServerAdapter(PlatformConfig(
        enabled=True, extra={"host": "127.0.0.1", "port": 8642, "key": "a" * 32}))


def request(api, *, label_id="", payload=None, lane="lane-a", namespace="companion"):
    value = SimpleNamespace(
        cookies={"honeyos_local": api._local_web_token}, remote="127.0.0.1", headers={}, app={},
        query={"lane": lane, "namespace": namespace, "limit": "50", "offset": "0"},
        match_info={"label_id": label_id},
    )
    if payload is not None:
        value.json = AsyncMock(return_value=payload)
    return value


def seed(home):
    store = UnderstandingStore(home / "understanding_v2.db")
    store.initialize()
    label_id = apply_proposal(
        store, owner="local-owner", lane="lane-a", namespace="companion",
        proposal=Proposal("propose", "learning_work_style", "learning", "mechanism",
                          "似乎偏好先理解机制", ("e1",), ()),
        evidence_meta={"e1": ("g1", "session-1", "r1", None)},
    )
    return label_id


@pytest.mark.asyncio
async def test_gateway_list_edit_suppress_restore_and_forget_are_durable(monkeypatch, tmp_path):
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    label_id = seed(tmp_path)
    api = adapter()
    listed = json.loads((await api._handle_companion_understanding(request(api))).text)
    assert listed["items"][0]["grade"] == "low"

    edited = await api._handle_companion_understanding_edit(
        request(api, label_id=label_id, payload={"body": "我更准确的表述"}))
    assert edited.status == 200
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    row = store.list_labels("local-owner", "lane-a", "companion")[0]
    assert row["body"] == "我更准确的表述" and row["grade"] == "low"

    for action, expected_state in (("suppress", "user_suppressed"),
                                   ("restore", "needs_reassessment"),
                                   ("forget", "user_suppressed")):
        response = await api._handle_companion_understanding_action(
            request(api, label_id=label_id, payload={"action": action}))
        assert response.status == 200
        row = store.list_labels("local-owner", "lane-a", "companion")[0]
        assert row["state"] == expected_state
        if action == "restore":
            assert row["grade"] == "low"
    assert store.list_labels("local-owner", "lane-a", "companion")[0]["body"] == ""


@pytest.mark.asyncio
async def test_gateway_scope_mismatch_is_not_disclosed(monkeypatch, tmp_path):
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    label_id = seed(tmp_path)
    api = adapter()
    response = await api._handle_companion_understanding_detail(
        request(api, label_id=label_id, lane="another-lane"))
    assert response.status == 404
