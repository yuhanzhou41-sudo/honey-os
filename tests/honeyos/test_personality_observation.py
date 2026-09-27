from __future__ import annotations

from honeyos.companion.personality_candidates import PersonalityCandidateStore
from honeyos.companion.personality_observation import detect_observation_signals
from honeyos.companion.personality_observation_hook import (
    capture_completed_turn_observation,
)


def test_preference_is_eligible():
    result = detect_observation_signals(
        user_text="Which do you like?",
        assistant_text="I prefer the second approach.",
    )
    assert result.eligible is True
    assert result.flags == ("preference",)


def test_disagreement_is_eligible():
    result = detect_observation_signals(
        user_text="Do you agree?",
        assistant_text="I disagree with that framing.",
    )
    assert result.eligible is True
    assert "disagreement" in result.flags


def test_user_personality_feedback_is_eligible_even_if_assistant_is_plain():
    result = detect_observation_signals(
        user_text="我觉得你最近说话方式更直接了。",
        assistant_text="我明白你的意思。",
    )
    assert result.eligible is True
    assert result.flags == ("explicit_user_feedback",)


def test_code_dump_without_signal_is_skipped():
    result = detect_observation_signals(
        user_text="Give me the code.",
        assistant_text="```python\nprint('x')\n```",
    )
    assert result.eligible is False
    assert result.flags == ()


def test_empty_assistant_turn_is_skipped():
    result = detect_observation_signals(
        user_text="hello",
        assistant_text="",
    )
    assert result.eligible is False


def test_hook_captures_without_creating_candidate(tmp_path):
    result = capture_completed_turn_observation(
        tmp_path,
        session_id="session-1",
        user_reference="u1",
        assistant_reference="a1",
        user_text="Which one do you like?",
        assistant_text="I prefer the second approach.",
    )

    assert result["captured"] is True
    assert result["signal_flags"] == ["preference"]

    store = PersonalityCandidateStore(tmp_path)
    assert store.pending_observation_count() == 1
    assert store.list_candidates() == []


def test_hook_skips_low_signal_turn(tmp_path):
    result = capture_completed_turn_observation(
        tmp_path,
        user_text="Summarize.",
        assistant_text="PASS: summary completed.",
    )

    assert result["captured"] is False
    store = PersonalityCandidateStore(tmp_path)
    # Store stays lazy because no eligible observation was captured.
    assert not store.db_path.exists()


def test_hook_is_fail_open(monkeypatch, tmp_path):
    from honeyos.companion import personality_observation_hook as hook

    class BrokenStore:
        def __init__(self, home):
            raise RuntimeError("boom")

    monkeypatch.setattr(hook, "PersonalityCandidateStore", BrokenStore)

    result = hook.capture_completed_turn_observation(
        tmp_path,
        user_text="Which?",
        assistant_text="I prefer this one.",
    )

    assert result["captured"] is False
    assert "boom" in result["error"]


def test_agent_hook_coerces_dict_user_message(monkeypatch, tmp_path):
    from honeyos.companion import personality_observation_hook as hook

    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))

    class Agent:
        session_id = "session-runtime"

    result = hook.capture_completed_agent_turn_observation(
        Agent(),
        turn_id="turn-1",
        user_message={"role": "user", "content": "Which one do you like?"},
        assistant_response="I prefer the second approach.",
    )

    assert result["captured"] is True
    store = PersonalityCandidateStore(tmp_path)
    rows = store.list_pending_observations()
    assert len(rows) == 1
    assert rows[0]["session_id"] == "session-runtime"
    assert rows[0]["user_reference"] == "turn-1:user"
    assert rows[0]["assistant_reference"] == "turn-1:assistant"
