from __future__ import annotations

from pathlib import Path

import honeyos.agent.turn_finalizer as turn_finalizer


def test_saved_reply_persist_precedes_companion_state_hooks():
    """S3.1: autonomous personality observation is now wired after persist.

    The companion state block (momentary_state + personality observation +
    reflection trigger) runs after _persist_session so we never learn from an
    unsaved or partially-persisted reply.
    """
    source = Path(turn_finalizer.__file__).read_text(encoding="utf-8")

    persist_idx = source.index("agent._persist_session(messages, conversation_history)")
    hook_idx = source.index("update_momentary_state_from_turn(")
    context_idx = source.index("# Context engine observation hook:")

    assert persist_idx < hook_idx < context_idx
    # S3.1: autonomous personality observation capture IS wired in the
    # companion state block (model-free, no extra LLM per turn).
    assert "capture_completed_agent_turn_observation(" in source
    assert "maybe_start_background_personality_reflection(" in source
    # Post-hoc physiology queue remains unwired in production (S3 decision).
    assert "enqueue_completed_reply(" not in source


def test_runtime_hook_is_guarded_by_completed_persisted_turn_conditions():
    source = Path(turn_finalizer.__file__).read_text(encoding="utf-8")

    assert "and completed\n        and normal_text_response" in source
    assert "and not interrupted\n        and not _personality_persist_failed" in source
    assert 'str(_err).startswith("persist_session:")' in source
