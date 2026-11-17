from __future__ import annotations

from pathlib import Path

import honeyos.agent.turn_finalizer as turn_finalizer


def test_personality_observation_hook_runs_after_persist_and_before_context_engine():
    source = Path(turn_finalizer.__file__).read_text(encoding="utf-8")

    persist_idx = source.index("agent._persist_session(messages, conversation_history)")
    hook_idx = source.index("capture_completed_agent_turn_observation")
    context_idx = source.index("# Context engine observation hook:")

    assert persist_idx < hook_idx < context_idx


def test_runtime_hook_is_guarded_by_completed_persisted_turn_conditions():
    source = Path(turn_finalizer.__file__).read_text(encoding="utf-8")

    assert "and completed\n        and normal_text_response" in source
    assert "and not interrupted\n        and not _personality_persist_failed" in source
    assert 'str(_err).startswith("persist_session:")' in source
