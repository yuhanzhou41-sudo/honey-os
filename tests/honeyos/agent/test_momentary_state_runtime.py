
from pathlib import Path

import honeyos.agent.turn_finalizer as turn_finalizer
import honeyos.companion.profile as profile


def test_turn_finalizer_updates_momentary_state_after_persist_guard():
    source = Path(turn_finalizer.__file__).read_text(encoding="utf-8")
    persist_guard = source.index(
        "and not interrupted\n        and not _personality_persist_failed"
    )
    update_call = source.index("update_momentary_state_from_turn(")
    observation_call = source.index("# Context engine observation hook:")
    assert persist_guard < update_call < observation_call


def test_profile_note_includes_momentary_state_only_via_dedicated_note():
    source = Path(profile.__file__).read_text(encoding="utf-8")
    assert "momentary_state_note(home)" in source
    assert "(base, promoted, momentary)" in source
