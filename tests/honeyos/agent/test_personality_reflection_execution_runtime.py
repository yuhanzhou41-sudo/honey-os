from __future__ import annotations

from pathlib import Path

import honeyos.agent.turn_finalizer as turn_finalizer


def test_runtime_starts_reflection_only_after_observation_capture():
    source = Path(turn_finalizer.__file__).read_text(encoding="utf-8")

    capture_idx = source.index("capture_completed_agent_turn_observation(")
    trigger_idx = source.index("maybe_start_background_personality_reflection(")

    assert capture_idx < trigger_idx
    assert 'if _personality_observation_result.get("captured"):' in source
