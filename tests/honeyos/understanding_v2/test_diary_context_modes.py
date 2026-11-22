import json
from datetime import datetime, timezone

from honeyos.companion.diary_automation import build_diary_messages
from honeyos.companion.momentary_state import update_momentary_state_from_turn
from honeyos.understanding.u2_store import UnderstandingStore


def test_diary_a_b_c_context_is_unchanged_by_u2_or_momentary_state(tmp_path):
    profile = {"companion_name": "Honey", "personality": "温和"}
    transcript = [{"role": "user", "content": "今天完成了复习", "timestamp": "2026-11-22T20:00:00+08:00"}]
    fixed = datetime(2026, 11, 22, 21, 0, tzinfo=timezone.utc)
    a = build_diary_messages(target_date="2026-11-22", companion_profile=profile,
                             user_entries=(), transcript=transcript, current_time=fixed)

    # B: U2 exists but neutral/not connected to diary.
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    store.initialize()
    b = build_diary_messages(target_date="2026-11-22", companion_profile=profile,
                             user_entries=(), transcript=transcript, current_time=fixed)

    # C: a valid synthetic momentary state exists, but diary does not read it.
    update_momentary_state_from_turn(tmp_path, assistant_response="我很开心，也很好奇。",
                                     turn_id="synthetic", now=fixed)
    c = build_diary_messages(target_date="2026-11-22", companion_profile=profile,
                             user_entries=(), transcript=transcript, current_time=fixed)
    assert a == b == c
    payload = json.loads(a[1]["content"])
    assert set(payload) == {"date", "companion_profile", "new_user_diary_entries", "conversation"}
    assert "今天完成了复习" in a[1]["content"]


def test_diary_prompt_does_not_claim_profile_or_memory_is_todays_event():
    messages = build_diary_messages(target_date="2026-11-22",
                                    companion_profile={"personality": "温和"},
                                    user_entries=(), transcript=[],
                                    current_time=datetime(2026, 11, 22, tzinfo=timezone.utc))
    system = messages[0]["content"]
    assert "Only new_user_diary_entries and conversation rows" in system
    assert "Do not treat profile information, general knowledge, memories" in system
