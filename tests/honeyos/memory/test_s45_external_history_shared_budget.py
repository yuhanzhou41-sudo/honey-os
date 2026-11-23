"""S4.5 Task D: DeepSeek + Study external history share one hard cap.

DeepSeek imports and (hypothetical/ future) Study external material are both
user-owned ``memory_origin='external'`` episodes.  They are retrieved by one
source-agnostic retriever, so the ``max_results`` / ``char_budget`` limits are
shared across *all* external sources rather than applied per source.  These
tests pin that contract; no production code change is required because the
retriever already ranks the whole external pool together.
"""

from __future__ import annotations

from pathlib import Path

from honeyos.memory.repository import CognitiveMemoryRepository
from honeyos.memory.runtime_context import build_silent_memory_context
from honeyos.memory.runtime_shadow import CognitiveMemoryShadowRetriever


def _repo(tmp_path: Path) -> CognitiveMemoryRepository:
    return CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")


def _add(repo, *, eid: str, summary: str, source_system: str, source_key: str):
    return repo.create_episode(
        episode_id=eid,
        episode_type="historical_external",
        summary=summary,
        memory_origin="external",
        source_system=source_system,
        source_scope="historical_import",
        source_key=source_key,
    )


def test_deepseek_and_study_share_one_result_and_char_budget(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="ds_1", summary="HoneyOS 记忆系统 DeepSeek 讨论一。", source_system="deepseek", source_key="ds-1")
    _add(repo, eid="ds_2", summary="HoneyOS 记忆系统 DeepSeek 讨论二。", source_system="deepseek", source_key="ds-2")
    _add(repo, eid="ds_3", summary="HoneyOS 记忆系统 DeepSeek 讨论三。", source_system="deepseek", source_key="ds-3")
    _add(repo, eid="st_1", summary="HoneyOS 记忆系统 Study 学习记录一。", source_system="study", source_key="st-1")
    _add(repo, eid="st_2", summary="HoneyOS 记忆系统 Study 学习记录二。", source_system="study", source_key="st-2")
    _add(repo, eid="st_3", summary="HoneyOS 记忆系统 Study 学习记录三。", source_system="study", source_key="st-3")

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "HoneyOS 记忆系统", write_audit=False
    )

    # One shared cap across all external sources, not 3 per source.
    assert len(result.selected) <= 3
    assert result.total_char_cost <= 900
    assert {item.source_system for item in result.selected} <= {"deepseek", "study"}
    # Source identity is never rewritten.
    for item in result.selected:
        assert item.source_system in {"deepseek", "study"}


def test_cross_source_duplicate_summary_deduped(tmp_path):
    repo = _repo(tmp_path)
    shared = "用户在一次长途骑行后决定重新规划每周训练。"
    _add(repo, eid="ds_dup", summary=shared, source_system="deepseek", source_key="ds-dup")
    _add(repo, eid="st_dup", summary=shared, source_system="study", source_key="st-dup")

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "长途骑行 训练计划", write_audit=False
    )

    ids = [item.id for item in result.selected]
    assert len(ids) == 1
    assert ids[0] in {"ds_dup", "st_dup"}


def test_suppressed_study_source_is_never_injected(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="st_live", summary="HoneyOS 记忆系统学习记录保留。", source_system="study", source_key="st-live")
    _add(repo, eid="st_dead", summary="HoneyOS 记忆系统学习记录已删除。", source_system="study", source_key="st-dead")
    repo.create_tombstone(
        scope="source", source_system="study", source_id="st-dead",
        reason="user_explicit_forget",
    )

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "HoneyOS 记忆系统", write_audit=False
    )

    assert all(item.id != "st_dead" for item in result.selected)


def test_no_relevance_match_injects_nothing(tmp_path):
    repo = _repo(tmp_path)
    _add(repo, eid="ds_1", summary="HoneyOS 记忆系统讨论。", source_system="deepseek", source_key="ds-1")
    _add(repo, eid="st_1", summary="HoneyOS 记忆系统学习记录。", source_system="study", source_key="st-1")

    result = CognitiveMemoryShadowRetriever(repo).retrieve(
        "今天午饭吃什么", write_audit=False
    )

    assert result.selected == ()
    assert result.total_char_cost == 0


def test_context_merge_caps_shared_external_payload(tmp_path):
    repo = _repo(tmp_path)
    long_tail = "很长的外部历史记录。" * 60
    for idx in range(3):
        _add(
            repo, eid=f"ds_{idx}", summary="记忆系统 " + long_tail,
            source_system="deepseek", source_key=f"ds-{idx}",
        )
    for idx in range(3):
        _add(
            repo, eid=f"st_{idx}", summary="记忆系统 " + long_tail,
            source_system="study", source_key=f"st-{idx}",
        )

    retrieved = CognitiveMemoryShadowRetriever(repo).retrieve(
        "记忆系统", write_audit=False
    )
    context = build_silent_memory_context(
        query="记忆系统",
        selected_memories=retrieved.selected,
        current_turn_text="记忆系统",
    )

    assert len(context.included) <= 3
    assert context.memory_chars <= 700
