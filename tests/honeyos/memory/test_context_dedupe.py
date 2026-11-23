from __future__ import annotations

import pytest

from honeyos.agent.turn_context import (
    drop_known_continuity_entries,
    drop_profile_fields_already_in_system_prompt,
)
from honeyos.memory.repository import CognitiveMemoryRepository
from honeyos.memory.runtime_context import run_silent_memory_context_shadow
from honeyos.memory.runtime_shadow import ShadowCandidate, ShadowRetrievalResult

PROMPT = (
    "## FORMED COMPANION IDENTITY\n"
    "<!-- honeyos-companion-profile:start -->\n"
    "- companion_name: 小甜\n"
    "- personality: 温柔\n"
    "- user_nickname: 阿泽\n"
    "<!-- honeyos-companion-profile:end -->\n"
)

PROFILE_NOTE = (
    "[HoneyOS 已确认伴侣档案：以下字段来自用户明确设置，优先于默认人格。"
    "自然遵循，不要机械复述。]\n"
    "- 伴侣名字: 小甜\n"
    "- 伴侣人格: 温柔\n"
    "- 用户接受的称呼: 阿泽"
)


def test_profile_fields_already_in_prompt_are_dropped():
    assert drop_profile_fields_already_in_system_prompt(PROFILE_NOTE, PROMPT) == ""


def test_changed_profile_field_is_kept():
    changed = PROFILE_NOTE.replace("- 伴侣名字: 小甜", "- 伴侣名字: 小星")
    kept = drop_profile_fields_already_in_system_prompt(changed, PROMPT)
    assert "伴侣名字: 小星" in kept
    assert "伴侣人格" not in kept
    assert "用户接受的称呼" not in kept


def test_non_profile_notes_survive_dedupe():
    notes = "[Runtime time] 2030-01-01 08:00\n\n" + PROFILE_NOTE
    kept = drop_profile_fields_already_in_system_prompt(notes, PROMPT)
    assert kept == "[Runtime time] 2030-01-01 08:00"


def test_repeated_rerun_does_not_duplicate_identity():
    once = drop_profile_fields_already_in_system_prompt(PROFILE_NOTE, PROMPT)
    twice = drop_profile_fields_already_in_system_prompt(once, PROMPT)
    assert once == twice == ""


CONTINUITY_BLOCK = (
    "[HoneyOS 关系连续性记忆：以下条目来自本地记录，仅在与当前消息相关时自然使用。\n"
    "不得据此推断或升级用户的身份、感情、关系、依赖、诊断或长期边界。\n"
    "条目 ID 可用于完成、纠正或忘记记忆。]\n"
    "- [mem_1] 真实共同经历：用户喜欢猫\n"
    "- [mem_2] 真实共同经历：用户养了一只橘猫"
)


def test_same_continuity_id_is_not_sent_twice():
    kept = drop_known_continuity_entries(CONTINUITY_BLOCK, "- [mem_1] 真实共同经历：用户喜欢猫")
    assert "[mem_1]" not in kept
    assert "[mem_2]" in kept


def test_distinct_continuity_ids_are_preserved():
    kept = drop_known_continuity_entries(CONTINUITY_BLOCK, "- [mem_9] 其他经历：无关")
    assert "[mem_1]" in kept and "[mem_2]" in kept


def test_fully_covered_continuity_block_is_skipped():
    known = "- [mem_1] x\n- [mem_2] y"
    assert drop_known_continuity_entries(CONTINUITY_BLOCK, known) == ""


def test_cognitive_skips_summary_already_delivered_by_continuity(tmp_path):
    """F2.2 exclude_summaries already dedupes Continuity vs Cognitive."""
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    repo.create_episode(
        episode_id="m1",
        episode_type="historical_external",
        summary="用户喜欢猫",
        occurred_at="2024-04-13T19:00:00+08:00",
        memory_origin="external",
        source_system="deepseek",
        source_scope="historical_import",
        source_key="source-m1",
        metadata={"access": {"owner": "User", "lane": "lane-a", "session_scope": "lane",
                             "chat_type": "dm", "purposes": ["chat"]}},
    )
    candidate = ShadowCandidate(
        id="m1",
        source_system="deepseek",
        source_key="source-m1",
        partition="personal",
        score=5.0,
        reason="lexical:test",
        selected=True,
        char_cost=6,
        summary_preview="用户喜欢猫",
    )
    shadow = ShadowRetrievalResult(
        query="用户喜欢什么",
        namespace="general",
        selected=(candidate,),
        rejected=(),
        total_char_cost=6,
    )
    context = run_silent_memory_context_shadow(
        shadow,
        session_id="s1",
        turn_id="t1",
        repository=repo,
        audit_path=tmp_path / "audit.jsonl",
        structured_context=CONTINUITY_BLOCK,
    )
    assert context.included == ()
    assert "duplicate_context" in {item.reason for item in context.rejected}


def test_duplicate_summary_from_distinct_sources_is_not_merged(tmp_path):
    """Similar text with a different id stays selectable when it is new."""
    from honeyos.memory.runtime_context import build_silent_memory_context

    candidate = {
        "id": "m2",
        "summary_preview": "用户养了一只橘猫",
        "runtime_namespace": "general",
        "source_system": "deepseek",
        "source_key": "source-m2",
    }
    context = build_silent_memory_context(
        query="猫",
        selected_memories=[candidate],
        current_turn_text="猫",
        exclude_summaries=["用户喜欢猫"],
    )
    assert [item.memory_id for item in context.included] == ["m2"]


@pytest.mark.parametrize("known", ["", "no entries here"])
def test_dedupe_is_noop_without_known_entries(known):
    assert drop_known_continuity_entries(CONTINUITY_BLOCK, known) == CONTINUITY_BLOCK
