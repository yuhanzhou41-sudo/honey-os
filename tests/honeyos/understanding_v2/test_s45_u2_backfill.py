"""S4.5 Task B: one-off evaluation of pre-existing native memories.

The run reuses the existing proposal contract and ``apply_proposal`` write
path.  These tests prove it (a) never re-creates native memories, (b) persists
real labels/evidence into the U2 store, (c) is read-only in dry-run mode, and
(d) skips memories without resolvable original user text.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.understanding import u2_backfill

LANE = "agent:main:api_server:dm:local-owner"
NS = "general"


def _state_db(home: Path) -> None:
    conn = sqlite3.connect(home / "state.db")
    conn.execute("""CREATE TABLE messages(
        id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT)""")
    conn.executemany("INSERT INTO messages VALUES(?,?,?,?)", [
        (10, "s1", "user", "我学东西喜欢先弄懂原理，再记结论"),
        (11, "s1", "assistant", "嗯，那我们先讲原理"),
        (12, "s2", "user", "复习时我也习惯先画知识框架"),
    ])
    conn.commit()
    conn.close()


def _seed(home: Path) -> tuple[str, str]:
    store = StructuredMemoryStore(home)
    first = store.record(
        lane_key=LANE, kind="episode", content="用户先理解原理再记结论",
        evidence="user_stated", source_session_id="s1", importance="high",
        created_by="background", now=datetime.now(timezone.utc),
        source_message_ids=(10, 11),
    )
    second = store.record(
        lane_key=LANE, kind="episode", content="用户复习先画框架",
        evidence="user_stated", source_session_id="s2", importance="high",
        created_by="background", now=datetime.now(timezone.utc),
        source_message_ids=(12,),
    )
    return first.id, second.id


def _fake_runtime() -> dict[str, str]:
    return {"provider": "fake", "model": "fake-model"}


def _bind_fake_call(monkeypatch, *, proposals=1):
    async def _call(*, system, user, provider, model, api_mode="", retries=0):
        payload = json.loads(user)
        refs = [item["ref"] for item in payload["evidence"]]
        items = []
        if proposals:
            items.append({
                "operation": "propose",
                "category_id": "learning_work_style",
                "scope_key": NS,
                "canonical_key": "mechanism_first",
                "text": "用户倾向先理解原理再记结论",
                "support_refs": refs[:proposals],
                "counter_refs": [],
            })
        return json.dumps({"proposals": items}, ensure_ascii=False)

    monkeypatch.setattr(u2_backfill, "_runtime", _fake_runtime)
    monkeypatch.setattr(u2_backfill, "build_proposal_call", lambda runtime: _call)


def test_dry_run_is_read_only_and_reports_candidates(tmp_path, monkeypatch):
    _state_db(tmp_path)
    _seed(tmp_path)
    monkeypatch.setattr(u2_backfill, "_runtime", _fake_runtime)
    report = u2_backfill.run(tmp_path, lane=LANE, namespace=NS, execute=False)
    assert report.found == 2 and report.sent == 2 and report.calls == 0
    assert report.remaining == 2
    # Dry run must not create the U2 store.
    assert not (tmp_path / "understanding_v2.db").exists()


def test_execute_persists_labels_without_duplicating_memories(tmp_path, monkeypatch):
    _state_db(tmp_path)
    first_id, second_id = _seed(tmp_path)
    _bind_fake_call(monkeypatch, proposals=2)
    report = u2_backfill.run(tmp_path, lane=LANE, namespace=NS, execute=True)
    assert report.calls == 1
    assert report.new_labels == 1
    assert report.relations >= 1
    assert report.remaining == 0
    assert not report.errors

    conn = sqlite3.connect(tmp_path / "understanding_v2.db")
    conn.row_factory = sqlite3.Row
    labels = conn.execute("SELECT * FROM labels").fetchall()
    assert len(labels) == 1
    assert labels[0]["body"] == "用户倾向先理解原理再记结论"
    refs = {row["evidence_ref"] for row in conn.execute(
        "SELECT evidence_ref FROM evidence WHERE label_id=?", (labels[0]["id"],))}
    conn.close()
    assert refs == {f"continuity:{first_id}", f"continuity:{second_id}"}

    # Native memories are untouched (not re-created, not rewritten).
    memories = sqlite3.connect(tmp_path / "continuity.db")
    assert memories.execute(
        "SELECT COUNT(*) FROM structured_memories").fetchone()[0] == 2
    memories.close()


def test_unresolvable_sources_are_ineligible_and_never_sent(tmp_path, monkeypatch):
    _state_db(tmp_path)
    store = StructuredMemoryStore(tmp_path)
    store.record(
        lane_key=LANE, kind="episode", content="来源消息已被清理",
        evidence="user_stated", source_session_id="s9", importance="high",
        created_by="background", now=datetime.now(timezone.utc),
        source_message_ids=(999,),
    )
    monkeypatch.setattr(u2_backfill, "_runtime", _fake_runtime)
    report = u2_backfill.run(tmp_path, lane=LANE, namespace=NS, execute=False)
    assert report.found == 1 and report.ineligible == 1 and report.sent == 0


def test_already_cited_memory_is_not_reprocessed(tmp_path, monkeypatch):
    _state_db(tmp_path)
    _seed(tmp_path)
    _bind_fake_call(monkeypatch, proposals=2)
    u2_backfill.run(tmp_path, lane=LANE, namespace=NS, execute=True)
    report = u2_backfill.run(tmp_path, lane=LANE, namespace=NS, execute=False)
    assert report.already_processed == 2
    assert report.sent == 0 and report.remaining == 0
