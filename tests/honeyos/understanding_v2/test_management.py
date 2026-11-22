from datetime import datetime, timezone

import pytest

from honeyos.understanding.u2_contracts import Proposal
from honeyos.understanding.u2_maintenance import apply_proposal
from honeyos.understanding.u2_manage import edit, explain, forget, restore, suppress
from honeyos.understanding.u2_store import UnderstandingStore


def seeded(tmp_path):
    store = UnderstandingStore(tmp_path / "u2.db")
    store.initialize()
    proposal = Proposal("propose", "learning_work_style", "learning", "mechanism",
                        "似乎偏好先理解机制", ("e1",), ())
    label_id = apply_proposal(store, owner="local-owner", lane="lane-a", namespace="companion",
                              proposal=proposal,
                              evidence_meta={"e1": ("g1", "s1", "r1", datetime.now(timezone.utc))})
    return store, label_id


def test_management_is_owner_lane_namespace_scoped(tmp_path):
    store, label_id = seeded(tmp_path)
    before = store.policy_epoch()
    with pytest.raises(PermissionError):
        suppress(store, label_id, owner="other", lane="lane-a", namespace="companion")
    assert store.policy_epoch() == before
    with pytest.raises(PermissionError):
        explain(store, label_id, owner="local-owner", lane="lane-b", namespace="companion")


def test_edit_suppress_restore_forget_keep_distinct_semantics(tmp_path):
    store, label_id = seeded(tmp_path)
    scope = dict(owner="local-owner", lane="lane-a", namespace="companion")
    edit(store, label_id, "我更准确的表述是先看机制再练习", **scope)
    edited = explain(store, label_id, **scope)
    assert edited["label"]["grade"] == "low"
    assert edited["versions"][0]["actor"] == "user_edit"
    suppress(store, label_id, **scope)
    assert explain(store, label_id, **scope)["label"]["body"] == ""
    restore(store, label_id, **scope)
    restored = explain(store, label_id, **scope)["label"]
    assert restored["state"] == "needs_reassessment" and restored["grade"] == "low"
    forget(store, label_id, **scope)
    forgotten = explain(store, label_id, **scope)
    assert forgotten["label"]["state"] == "user_suppressed"
    assert forgotten["label"]["body"] == "" and not forgotten["evidence"]


def test_pagination_is_bounded(tmp_path):
    store, _ = seeded(tmp_path)
    rows, total = store.page_labels("local-owner", "lane-a", "companion", limit=10_000)
    assert total == 1 and len(rows) == 1
    assert not store.page_labels("local-owner", "other", "companion")[0]


def test_existing_gateway_registers_management_routes_once():
    from honeyos.gateway.config import PlatformConfig
    from honeyos.gateway.platforms.api_server import APIServerAdapter
    adapter = APIServerAdapter(PlatformConfig(
        enabled=True, extra={"host": "127.0.0.1", "port": 8642, "key": "a" * 32}))
    routes = [(method, path) for method, path, _ in adapter._http_route_table()]
    expected = (
        ("GET", "/api/companion/understanding"),
        ("GET", "/api/companion/understanding/{label_id}"),
        ("PATCH", "/api/companion/understanding/{label_id}"),
        ("POST", "/api/companion/understanding/{label_id}/action"),
    )
    assert all(routes.count(route) == 1 for route in expected)


def test_read_only_ui_does_not_initialize_store_when_off(monkeypatch, tmp_path):
    from honeyos.gateway.platforms.api_server import APIServerAdapter
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    assert APIServerAdapter._understanding_store() is None
    assert not (tmp_path / "understanding_v2.db").exists()
