"""S4.5 graph API tests (direct handler calls against a temp home)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from honeyos.runtime.web_routers import understanding as u


def _build_home(tmp: Path) -> Path:
    u2 = sqlite3.connect(tmp / "understanding_v2.db")
    u2.execute("""CREATE TABLE labels(
        id TEXT PRIMARY KEY, owner TEXT, lane TEXT, namespace TEXT, category TEXT,
        scope_key TEXT, canonical_key TEXT, body TEXT, state TEXT, grade TEXT,
        revision INTEGER, policy_epoch INTEGER, created_at TEXT, updated_at TEXT)""")
    u2.execute("""CREATE TABLE evidence(
        label_id TEXT, evidence_ref TEXT, event_group TEXT, session_ref TEXT,
        relation TEXT, occurred_at TEXT, source_revision TEXT)""")
    u2.execute(
        "INSERT INTO labels VALUES('ul_1','local-owner','chat','general',"
        "'behavior_pattern','workflow','prefers_planning','用户倾向先规划',"
        "'supported','medium',1,0,'2026-08-07','2026-08-07')")
    u2.execute(
        "INSERT INTO evidence VALUES('ul_1','continuity:m_active','m_active','s1',"
        "'support','2026-08-07','2026-08-07')")
    u2.execute(
        "INSERT INTO evidence VALUES('ul_1','continuity:m_forgotten','m_forgotten','s1',"
        "'support','2026-08-06','2026-08-06')")
    u2.commit()
    u2.close()

    c = sqlite3.connect(tmp / "continuity.db")
    c.execute("""CREATE TABLE structured_memories(
        id TEXT PRIMARY KEY, lane_key TEXT, kind TEXT, content TEXT, status TEXT,
        created_at TEXT, source_session_id TEXT)""")
    c.execute("""CREATE TABLE structured_memory_emotional_imprints(
        memory_id TEXT PRIMARY KEY, lane_key TEXT, kind TEXT, status TEXT,
        dominant_axis TEXT, dominant_label TEXT, basis_axes_json TEXT,
        basis_turn_ids_json TEXT, formed_at TEXT, recorded_at TEXT,
        distillation_run_id TEXT, evidence_summary TEXT)""")
    c.execute("INSERT INTO structured_memories VALUES"
              "('m_active','chat','episode','我们一起制定了计划','active','2026-08-07','s1')")
    c.execute("INSERT INTO structured_memories VALUES"
              "('m_forgotten','chat','episode','用户不想保留','forgotten','2026-08-06','s1')")
    c.execute("INSERT INTO structured_memory_emotional_imprints VALUES"
              "('m_active','chat','episode','known','warmth','温暖','[]','[]',"
              "'2026-08-07','2026-08-07',NULL,'test')")
    c.commit()
    c.close()
    return tmp


@pytest.fixture()
def home(tmp_path, monkeypatch):
    _build_home(tmp_path)
    monkeypatch.setattr(u, "_home", lambda: tmp_path)
    return tmp_path


def test_graph_drops_forgotten_memory_and_keeps_imprint(home):
    out = u.get_understanding_graph(lane="", namespace="", limit=50, offset=0)
    assert out["total"] == 1
    label = out["labels"][0]
    refs = [e["ref"] for e in label["evidence"]]
    assert refs == ["continuity:m_active"]  # forgotten dropped
    mem = label["evidence"][0]["memory"]
    assert mem["kind"] == "episode"
    assert mem["imprint"]["status"] == "known"
    assert mem["imprint"]["label"] == "温暖"


def test_suppress_hides_body_but_keeps_label(home):
    u.suppress_understanding_label("ul_1")
    out = u.get_understanding_label("ul_1")
    assert out["state"] == "user_suppressed"
    assert out["suppressed"] is True
    assert out["text"] == ""  # body not leaked


def test_detach_evidence_removes_only_relation(home):
    res = u.detach_understanding_evidence("ul_1", ref="continuity:m_active")
    assert res["removed"] == 1
    out = u.get_understanding_label("ul_1")
    assert all(e["ref"] != "continuity:m_active" for e in out["evidence"])
    # label itself still exists
    assert out["id"] == "ul_1"


def test_missing_store_returns_empty_graph(tmp_path, monkeypatch):
    monkeypatch.setattr(u, "_home", lambda: tmp_path)
    assert u.get_understanding_graph(lane="", namespace="", limit=50, offset=0)["labels"] == []
