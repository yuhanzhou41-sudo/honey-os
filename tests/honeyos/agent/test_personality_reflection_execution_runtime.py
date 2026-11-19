from __future__ import annotations

from pathlib import Path

import honeyos.gateway.platforms.api_server as api_server


def test_runtime_starts_reflection_only_after_observation_capture():
    source = Path(api_server.__file__).read_text(encoding="utf-8")

    capture_idx = source.index("asyncio.to_thread(capture_liked_reply")
    trigger_idx = source.index("asyncio.to_thread(maybe_start_background_personality_reflection")

    assert capture_idx < trigger_idx
    assert 'if rating == "like":' in source
