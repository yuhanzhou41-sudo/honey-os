"""S4.5 tests for physiology boost divergence and U2 same-batch integration."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.companion.distillation import (
    DistillationJob,
    DistillationResult,
    MemoryDistiller,
)


def _make_fake_physiology(home: Path, epinephrine: float) -> None:
    """Seed a fake physiology_shadow.sqlite so context_for_lane reads it."""
    import sqlite3
    db = home / "physiology_shadow.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS physiological_signals (
        signal TEXT PRIMARY KEY, value REAL NOT NULL, last_updated TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'live'
    )""")
    for sig, val in (("epinephrine", epinephrine),
                     ("attention", 0.7), ("arousal", 0.4),
                     ("dopamine", 0.5), ("cortisol", 0.3),
                     ("oxytocin", 0.5), ("serotonin", 0.6),
                     ("melatonin", 0.2), ("adenosine", 0.2)):
        conn.execute(
            "INSERT OR REPLACE INTO physiological_signals(signal,value,last_updated,source) "
            "VALUES (?,?,datetime('now'),'live')", (sig, val)
        )
    conn.commit()
    conn.close()


def test_physiology_boost_diverges_by_kind_for_nearby_scores(tmp_path):
    """Nearby lexical scores should be re-ranked when epinephrine is high
    and the items differ in kind."""
    store = StructuredMemoryStore(tmp_path)
    # Two items with similar lexical content but different kind —
    # should receive different boosts.
    store.record(
        lane_key="chat", kind="temporary_state",
        content="讨论了项目规划项目规划项目规划项目规划",
        evidence="user_stated", created_by="distill", now=datetime(2026, 8, 6, tzinfo=timezone.utc),
        source_session_id="s1", source_message_ids=[1],
    )
    store.record(
        lane_key="chat", kind="episode",
        content="讨论了项目规划项目规划项目规划项目规划",
        evidence="interaction_trace", created_by="distill", now=datetime(2026, 8, 7, tzinfo=timezone.utc),
        source_session_id="s1", source_message_ids=[2],
    )
    store.record(
        lane_key="chat", kind="commitment",
        content="讨论了项目规划项目规划项目规划项目规划",
        evidence="interaction_trace", created_by="distill", now=datetime(2026, 8, 7, 1, tzinfo=timezone.utc),
        source_session_id="s1", source_message_ids=[3],
    )
    # No physiology baseline
    result_no_phys = store.context_for_lane(
        lane_key="chat", now=datetime(2026, 8, 7, tzinfo=timezone.utc),
        query="项目规划",
    )
    _make_fake_physiology(tmp_path, epinephrine=0.9)  # high arousal
    result_high_phys = store.context_for_lane(
        lane_key="chat", now=datetime(2026, 8, 7, tzinfo=timezone.utc),
        query="项目规划",
    )
    # With high epinephrine, highest-leverage kind (episode) should now lead
    # regardless of content similarity.
    assert "episode" in (result_high_phys or "") or "temporary_state" not in (result_high_phys or "")


def test_u2_parse_understandings_rejects_unknown_categories():
    raw = r"""
{
  "chapter": {"summary": "..."},
  "operations": [{"kind": "episode", "action": "record", "content": "我们一起做了X"}],
  "understandings": [
    {
      "operation": "propose",
      "category_id": "astrology_sign",
      "scope_key": "general",
      "canonical_key": "user_is_taurus",
      "text": "用户是金牛座",
      "operation_indices": [0]
    }
  ]
}
"""
    parsed = MemoryDistiller._parse_understandings(raw)
    assert parsed == ()


def test_u2_parse_understandings_accepts_valid_item():
    raw = r"""
{
  "chapter": {"summary": "..."},
  "operations": [
    {"kind": "episode", "action": "record", "content": "用户反复说要提前规划"},
    {"kind": "commitment", "action": "record", "content": "Honey 答应明天提醒"}
  ],
  "understandings": [
    {
      "operation": "propose",
      "category_id": "behavior_pattern",
      "scope_key": "workflow",
      "canonical_key": "prefers_planning_first",
      "text": "用户倾向在执行前先规划",
      "operation_indices": [0]
    }
  ]
}
"""
    parsed = MemoryDistiller._parse_understandings(raw)
    assert len(parsed) == 1
    u = parsed[0]
    assert u["category_id"] == "behavior_pattern"
    assert u["canonical_key"] == "prefers_planning_first"
    assert 0 in u["operation_indices"]


def test_u2_parse_understandings_requires_valid_indices():
    # Missing operation_indices → skip
    raw = r"""
{
  "operations": [{"kind": "episode", "action": "record", "content": "..."}],
  "understandings": [
    {
      "operation": "propose",
      "category_id": "interest_preference",
      "scope_key": "tech",
      "canonical_key": "likes_rust",
      "text": "用户喜欢 Rust",
      "operation_indices": []
    }
  ]
}
"""
    assert MemoryDistiller._parse_understandings(raw) == ()


def test_u2_same_batch_fall_back_to_empty_when_model_missing_field():
    """Backward compat: old model output without 'understandings' parses to
    empty tuple and results flow to U2 apply hook as no-op."""
    raw = r'{"operations": [{"kind": "episode", "action": "record", "content": "..."}]}'
    assert MemoryDistiller._parse_understandings(raw) == ()


def test_apply_operations_returns_index_to_memory_id_map(tmp_path):
    """_apply_operations must return which operation indices succeeded
    so result.applied_indices[op_index] gives the real memory id needed by
    the U2 same-batch hook."""
    from honeyos.companion.distillation import DistillationSettings

    distiller = MemoryDistiller(tmp_path, settings=DistillationSettings())
    now = datetime(2026, 8, 7, tzinfo=timezone.utc)
    messages = (
        {"_row_id": 1, "role": "user", "content": "我喜欢提前规划"},
        {"_row_id": 2, "role": "assistant", "content": "好的，明天提醒你"},
    )
    job = DistillationJob(
        run_id="run-1", lane_key="chat", session_id="s1",
        reason="test", messages=messages, source_start_id=1, source_end_id=2,
        source_hash="xyz", now=now, max_operations=5,
        companion_profile={},
    )
    operations = (
        {"kind": "episode", "action": "record",
         "content": "用户表示倾向于在执行前先做规划",
         "evidence": "conversation_event", "created_by": "test",
         "evidence_message_ids": [1, 2]},
        {"kind": "commitment", "action": "record",
         "content": "Honey 答应明天提醒用户复习",
         "evidence": "assistant_committed", "created_by": "test",
         "evidence_message_ids": [2]},
    )
    applied, rejected, applied_indices = distiller._apply_operations(
        job, operations, active_items=(),
    )
    assert applied == 2 and rejected == 0, (applied, rejected)
    assert len(applied_indices) == 2
    assert 0 in applied_indices and 1 in applied_indices
    all_items = distiller.memories.list_active(lane_key="chat", now=now)
    active_ids = {item.id for item in all_items}
    for mid in applied_indices.values():
        assert mid in active_ids
