
from datetime import datetime, timedelta, timezone

from honeyos.companion.momentary_state import (
    load_momentary_state,
    momentary_state_note,
    update_momentary_state_from_turn,
)


def test_explicit_curiosity_creates_temporary_state(tmp_path):
    now = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    state = update_momentary_state_from_turn(
        tmp_path,
        assistant_response="我其实挺好奇这个结果最后会变成什么样。",
        turn_id="t1",
        now=now,
    )
    assert state["axes"]["curiosity"] > 0
    assert "curious" in momentary_state_note(tmp_path, now=now)


def test_state_decays_over_time(tmp_path):
    start = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    update_momentary_state_from_turn(
        tmp_path,
        assistant_response="我其实挺好奇这个方向。",
        turn_id="t1",
        now=start,
    )
    immediate = load_momentary_state(tmp_path, now=start)["axes"]["curiosity"]
    later = load_momentary_state(
        tmp_path,
        now=start + timedelta(hours=3),
    )["axes"]["curiosity"]
    assert 0 < later < immediate
    assert abs(later - immediate * 0.5) < 0.02


def test_state_expires_after_long_idle_period(tmp_path):
    start = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    update_momentary_state_from_turn(
        tmp_path,
        assistant_response="我很开心，这个进展很好。",
        turn_id="t1",
        now=start,
    )
    expired = load_momentary_state(
        tmp_path,
        now=start + timedelta(hours=13),
    )
    assert max(expired["axes"].values()) == 0
    assert momentary_state_note(
        tmp_path,
        now=start + timedelta(hours=13),
    ) == ""


def test_neutral_turn_does_not_create_state_file(tmp_path):
    update_momentary_state_from_turn(
        tmp_path,
        assistant_response="测试通过，下一步可以继续。",
        turn_id="t1",
    )
    assert not (tmp_path / "companion" / "momentary_state.json").exists()


def test_user_state_is_not_inferred_from_user_message(tmp_path):
    state = update_momentary_state_from_turn(
        tmp_path,
        assistant_response="我知道了。",
        turn_id="t1",
    )
    assert max(state["axes"].values()) == 0


def test_positive_and_negative_state_counterbalance(tmp_path):
    now = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    positive = update_momentary_state_from_turn(
        tmp_path,
        assistant_response="我很开心，这个进展很好。",
        turn_id="t1",
        now=now,
    )
    assert positive["axes"]["positive_valence"] > 0

    negative = update_momentary_state_from_turn(
        tmp_path,
        assistant_response="我有点烦，这个地方确实不太对。",
        turn_id="t2",
        now=now + timedelta(minutes=1),
    )
    assert negative["axes"]["negative_valence"] > 0
    assert negative["axes"]["positive_valence"] < positive["axes"]["positive_valence"]

def test_curiosity_matches_common_chinese_self_expression(tmp_path):
    now = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)
    state = update_momentary_state_from_turn(
        tmp_path,
        assistant_response="我对这个结果很好奇。",
        turn_id="t-extra",
        now=now,
    )
    assert state["axes"]["curiosity"] > 0
