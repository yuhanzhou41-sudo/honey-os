
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from honeyos.companion.momentary_state import update_momentary_state_from_turn
from honeyos.companion.proactive_initiative import (
    evaluate_personal_initiative,
    seed_personal_initiative_if_due,
)


NOW = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, *, consented=True, idle_hours=2, minimum_interval_hours=3):
        self._prefs = {
            "consent_asked": True,
            "consented": consented,
            "daily_limit": 2,
            "minimum_interval_hours": minimum_interval_hours,
            "idle_hours": idle_hours,
            "quiet_start": "23:00",
            "quiet_end": "09:00",
        }
        self.channel = SimpleNamespace(
            last_user_message_at=NOW - timedelta(hours=3)
        )
        self.added = []

    def preferences_payload(self):
        return dict(self._prefs)

    def latest_channel(self):
        return self.channel

    def add_candidates(self, candidates):
        self.added.extend(candidates)
        return candidates


def _curious_state(home):
    update_momentary_state_from_turn(
        home,
        assistant_response="我其实挺好奇这个话题之后会怎么发展。",
        turn_id="t1",
        now=NOW - timedelta(hours=1),
    )


def test_consent_is_mandatory(tmp_path):
    _curious_state(tmp_path)
    store = FakeStore(consented=False)
    decision = evaluate_personal_initiative(tmp_path, store, now=NOW)
    assert decision.eligible is False
    assert decision.reason == "not_consented"


def test_owner_must_be_idle(tmp_path):
    _curious_state(tmp_path)
    store = FakeStore(idle_hours=2)
    store.channel.last_user_message_at = NOW - timedelta(minutes=30)
    decision = evaluate_personal_initiative(tmp_path, store, now=NOW)
    assert decision.eligible is False
    assert decision.reason == "owner_not_idle"


def test_neutral_state_does_not_force_engagement(tmp_path):
    store = FakeStore()
    decision = evaluate_personal_initiative(tmp_path, store, now=NOW)
    assert decision.eligible is False
    assert decision.reason == "no_genuine_initiative_signal"


def test_curiosity_can_seed_existing_topic_pool(tmp_path, monkeypatch):
    _curious_state(tmp_path)
    store = FakeStore()

    monkeypatch.setattr(
        "honeyos.companion.proactive_initiative._build_topic_candidate",
        lambda now: {"hook": "internal initiative"},
    )

    result = seed_personal_initiative_if_due(tmp_path, store, now=NOW)
    assert result["seeded"] is True
    assert store.added == [{"hook": "internal initiative"}]


def test_seed_cooldown_prevents_repeated_open_initiatives(tmp_path, monkeypatch):
    _curious_state(tmp_path)
    store = FakeStore()

    monkeypatch.setattr(
        "honeyos.companion.proactive_initiative._build_topic_candidate",
        lambda now: {"hook": "internal initiative"},
    )

    first = seed_personal_initiative_if_due(tmp_path, store, now=NOW)
    second = seed_personal_initiative_if_due(
        tmp_path, store, now=NOW + timedelta(hours=1)
    )
    assert first["seeded"] is True
    assert second["seeded"] is False
    assert second["reason"] == "initiative_seed_cooldown"
    assert len(store.added) == 1


def test_daily_limit_zero_disables_seed(tmp_path):
    _curious_state(tmp_path)
    store = FakeStore()
    store._prefs["daily_limit"] = 0
    decision = evaluate_personal_initiative(tmp_path, store, now=NOW)
    assert decision.eligible is False
    assert decision.reason == "daily_limit_zero"

def test_curiosity_remains_eligible_after_normal_idle_window(tmp_path):
    update_momentary_state_from_turn(
        tmp_path,
        assistant_response="我其实挺好奇这个话题之后会怎么发展。",
        turn_id="t-idle",
        now=NOW - timedelta(hours=2),
    )
    store = FakeStore(idle_hours=2)
    decision = evaluate_personal_initiative(tmp_path, store, now=NOW)
    assert decision.eligible is True
    assert decision.reason == "eligible"

def test_real_topic_pool_store_accepts_internal_initiative_candidate(tmp_path):
    from datetime import datetime, timezone

    from honeyos.companion.proactive_initiative import (
        _build_topic_candidate,
        _insert_topic_candidate,
    )
    from honeyos.companion.topic_pool import TopicPoolStore

    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    store = TopicPoolStore(tmp_path, now_fn=lambda: now)
    candidate = _build_topic_candidate(now)

    inserted = _insert_topic_candidate(store, candidate)

    assert isinstance(inserted, (list, tuple))
    assert inserted
    topic_id = inserted[0].id
    stored = store.get_topic(topic_id)

    assert stored is not None
    assert stored.id == topic_id
    assert stored.status == "open"
