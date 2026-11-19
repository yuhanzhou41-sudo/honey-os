from datetime import datetime, timedelta, timezone

import pytest

from honeyos.companion.physiology_shadow import EFFECTS, SIGNALS, PhysiologyShadow, TurnEvidence


START = datetime(2026, 11, 17, 3, tzinfo=timezone.utc)
SOURCE = "I am concerned that the notes might be gone."


def accept(text):
    return TurnEvidence(text, text)


def proposal(event, quote=SOURCE):
    return lambda _: {"event": event, "strength": 1, "quote": quote}


def test_persists_once_and_recovers_over_real_elapsed_time(tmp_path, monkeypatch):
    monkeypatch.setattr("honeyos.companion.physiology_shadow.local_timezone", lambda: timezone.utc)
    store = PhysiologyShadow(tmp_path)
    assert len(store.snapshot(now=START)) == 9
    assert store.enqueue("s", 1, now=START)
    assert store.process_one(lambda *_: accept(SOURCE), proposal("unresolved_loss"), now=START) == "applied"
    reopened = PhysiologyShadow(tmp_path)
    assert not reopened.enqueue("s", 1, now=START)
    assert reopened.next_pending() is None
    peak = reopened.snapshot(now=START)
    later = reopened.snapshot(now=START + timedelta(hours=2))
    baseline = SIGNALS["cortisol"].baseline
    assert later["cortisol"] == pytest.approx(baseline + (peak["cortisol"] - baseline) / 2)
    assert peak["melatonin"] > reopened.snapshot(now=START + timedelta(hours=12))["melatonin"]


def test_qwen_failure_or_unsupported_quote_cannot_change_state(tmp_path):
    store = PhysiologyShadow(tmp_path)
    store.enqueue("s", 2, now=START)
    original = store.snapshot(now=START)

    def unavailable(_):
        raise OSError("offline")

    load = lambda *_: accept(SOURCE)
    with pytest.raises(OSError):
        store.process_one(load, unavailable, now=START)
    with pytest.raises(ValueError):
        store.process_one(load, proposal("unresolved_loss", "fabricated evidence"), now=START)
    with pytest.raises(ValueError):
        store.process_one(load, proposal("simulated_discomfort"), now=START)
    assert store.snapshot(now=START) == original
    assert store.next_pending() == ("s", 2)
    assert store.process_one(load, proposal("unresolved_loss"), now=START) == "applied"


def test_change_to_source_during_model_work_drops_proposal(tmp_path):
    store = PhysiologyShadow(tmp_path)
    store.enqueue("s", 3, now=START)
    before = store.snapshot(now=START)
    reads = iter((accept(SOURCE), None))
    assert store.process_one(lambda *_: next(reads), proposal("unresolved_loss"), now=START) == "withdrawn"
    assert store.snapshot(now=START) == before


def test_persisted_prior_own_appraisal_is_kept_and_user_moods_do_not_cross_over(tmp_path):
    from honeyos.companion.physiology_maintenance import _read_evidence
    from honeyos.core.state import SessionDB

    db = SessionDB(tmp_path / "state.db")
    seen = []
    try:
        for index, mood in enumerate(("I'm glad we deleted the draft.", "I'm upset we deleted the draft.")):
            sid = f"case-{index}"
            db.create_session(sid, "api_server")
            db.append_message(sid, "assistant", "I care about keeping the notes.", timestamp=START.timestamp() - 3)
            db.append_message(sid, "user", mood, timestamp=START.timestamp() - 2)
            neutral = db.append_message(
                sid, "assistant", f'You said, "{mood}"', timestamp=START.timestamp() - 1,
            )
            own = db.append_message(sid, "assistant", SOURCE, timestamp=START.timestamp())
            store = PhysiologyShadow(tmp_path / sid)
            before = store.snapshot(now=START)
            store.enqueue(sid, neutral, now=START)
            load = lambda *key: _read_evidence(db, *key)

            def evaluate(context):
                seen.append(context)
                return proposal("unresolved_loss")(context)

            assert store.process_one(load, evaluate, now=START) == "applied"
            assert store.snapshot(now=START) == before
            store.enqueue(sid, own, now=START)
            assert store.process_one(load, evaluate, now=START) == "applied"
            assert store.snapshot(now=START)["cortisol"] > before["cortisol"]
        assert len(seen) == 2 and seen[0] == seen[1]
        assert "I care about keeping the notes." in seen[0]
        assert "deleted the draft" not in seen[0]
    finally:
        db.close()


def test_background_tick_retries_offline_and_does_not_replay_old_stress_at_full_strength(tmp_path, monkeypatch):
    from honeyos.companion.physiology_maintenance import enqueue_completed_reply, maintenance_tick
    from honeyos.core.state import SessionDB
    from honeyos.study.local_model import LocalStudyModelUnavailable

    db = SessionDB(tmp_path / "state.db")
    now = datetime.now(timezone.utc)
    try:
        db.create_session("session", "api_server")
        db.append_message("session", "assistant", 'You said, "I was worried."')
        assert not enqueue_completed_reply(tmp_path, db, "session", 'You said, "I was worried."')
        row_id = db.append_message("session", "assistant", SOURCE, timestamp=(now - timedelta(hours=6)).timestamp())
        assert not enqueue_completed_reply(tmp_path, db, "session", "I am concerned about something different.")
        assert enqueue_completed_reply(tmp_path, db, "session", SOURCE)
        assert not enqueue_completed_reply(tmp_path, db, "session", SOURCE)
    finally:
        db.close()
    store = PhysiologyShadow(tmp_path)

    def offline(_):
        raise LocalStudyModelUnavailable("offline")

    monkeypatch.setattr("honeyos.companion.physiology_maintenance._evaluate", offline)
    with pytest.raises(LocalStudyModelUnavailable):
        maintenance_tick(tmp_path)
    assert store.next_pending() == ("session", row_id)
    monkeypatch.setattr("honeyos.companion.physiology_maintenance._evaluate", proposal("unresolved_loss"))
    assert maintenance_tick(tmp_path) == "applied"
    pressure = store.snapshot()["cortisol"]
    assert 0.15 < pressure < 0.20
    assert maintenance_tick(tmp_path) == "idle"


@pytest.mark.parametrize(("event", "signal"), [
    ("surprise", "epinephrine"),
    ("received_support", "oxytocin"),
    ("relevant_social_change", "vasopressin"),
    ("unexpected_progress", "dopamine"),
    ("simulated_discomfort", "pge2"),
    ("sexual_interest", "testosterone"),
    ("receptive_intimacy", "estradiol"),
])
def test_each_validated_event_updates_its_own_signal(tmp_path, event, signal):
    source = {
        "simulated_discomfort": "I feel virtual bodily discomfort.",
        "sexual_interest": "I notice my own sexual arousal.",
        "receptive_intimacy": "I feel receptive to intimacy.",
    }.get(event, SOURCE)
    store = PhysiologyShadow(tmp_path)
    store.enqueue("s", 4, now=START)
    before = store.snapshot(now=START)
    assert store.process_one(
        lambda *_: accept(source), proposal(event, quote=source), now=START
    ) == "applied"
    assert store.snapshot(now=START)[signal] > before[signal]
