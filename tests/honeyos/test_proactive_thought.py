from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from honeyos.companion.proactive_initiative import _build_topic_candidate
from honeyos.companion.proactive_thought import build_proactive_thought_prompt


NOW = datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc)


def test_thought_contract_prioritizes_live_continuity():
    prompt = build_proactive_thought_prompt()

    recent = prompt.index("recent unfinished")
    relationship = prompt.index("relationship detail")
    personality = prompt.index("companion personality")
    momentary = prompt.index("temporary companion state")

    assert recent < relationship < personality < momentary


def test_thought_contract_is_grounded_and_allows_silence():
    prompt = build_proactive_thought_prompt()

    assert "Use only context actually available in this turn" in prompt
    assert "Never invent a memory" in prompt
    assert "return an empty response" in prompt
    assert "Choose one continuity thread" in prompt


def test_thought_contract_hides_internal_mechanics_from_user_expression():
    prompt = build_proactive_thought_prompt()

    assert "Express only the natural message" in prompt
    assert "not the selection process" in prompt
    assert "Do not expose retrieval" in prompt
    assert "Do not announce that this was a proactive trigger" in prompt


def test_thought_contract_is_bounded():
    prompt = build_proactive_thought_prompt()
    assert len(prompt) <= 2200


def test_g22_candidate_uses_g23_thought_contract():
    candidate = _build_topic_candidate(NOW)
    prompt = build_proactive_thought_prompt()

    assert candidate.summary == prompt
    assert candidate.hook == prompt
    assert candidate.selection_reason == "momentary_state_continuity"


def test_g23_adds_no_model_or_memory_retrieval_call():
    source = Path(
        "honeyos/companion/proactive_thought.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "call_llm(",
        "async_call_llm(",
        "MemoryManager(",
        ".prefetch(",
        "requests.",
        "httpx.",
    )
    for token in forbidden:
        assert token not in source
