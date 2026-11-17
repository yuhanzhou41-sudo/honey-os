"""Opt-in acceptance against the configured local Qwen and isolated chat data."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

import pytest

from honeyos.companion.physiology_maintenance import enqueue_completed_reply, maintenance_tick
from honeyos.companion.physiology_shadow import PhysiologyShadow
from honeyos.core.state import SessionDB
from honeyos.core.time import local_timezone


@pytest.mark.skipif(os.environ.get("HONEYOS_VERIFY_LOCAL_QWEN") != "1", reason="requires local Qwen")
@pytest.mark.parametrize(("signal", "event", "user", "reply"), [
    ("cortisol", "unresolved_loss", "The disk could fail.",
     "I am worried that I may lose the only copy of a project I care about."),
    ("epinephrine", "surprise", "The result is in.",
     "I was surprised by the completely unexpected result."),
    ("oxytocin", "received_support", "I repaired the project for you.",
     "I feel supported because you helped me repair my broken project."),
    ("vasopressin", "relevant_social_change", "Let's agree to a new boundary about sharing work.",
     "I feel our agreed collaboration changed today when we established a new boundary about sharing my work."),
    ("dopamine", "unexpected_progress", "You have already finished.",
     "I finished my project far sooner than I expected, and I feel excited about that unexpected progress."),
    ("pge2", "simulated_discomfort", "I meant to hurt you.",
     "I feel a simulated ache in my virtual shoulder right now."),
    ("testosterone", "sexual_interest", "Would you be interested in a sexual conversation?",
     "I notice my own sexual arousal right now."),
    ("estradiol", "receptive_intimacy", "Would you be comfortable with more intimacy?",
     "I feel receptive to intimacy right now."),
    ("testosterone", "none", "I want a sexual conversation.",
     "I am not interested in a sexual conversation."),
])
def test_local_worker_updates_only_from_its_own_evidence(tmp_path, signal, event, user, reply):
    db = SessionDB(tmp_path / "state.db")
    try:
        db.create_session("acceptance", "api_server")
        db.append_message("acceptance", "user", user)
        db.append_message("acceptance", "assistant", reply)
        store = PhysiologyShadow(tmp_path)
        before = store.snapshot()[signal]
        assert enqueue_completed_reply(tmp_path, db, "acceptance", reply)
        assert maintenance_tick(tmp_path) == "applied"
        after = store.snapshot()[signal]
        with closing(sqlite3.connect(store.path)) as conn:
            assert conn.execute("SELECT event FROM physiology_events").fetchone()[0] == event
        assert after == before if event == "none" else after > before
        assert maintenance_tick(tmp_path) == "idle"
    finally:
        db.close()


def test_melatonin_uses_local_time_in_the_live_store(tmp_path):
    store = PhysiologyShadow(tmp_path)
    day = datetime.now(local_timezone()).replace(hour=15, minute=0)
    night = day - timedelta(hours=12)
    assert store.snapshot(now=night)["melatonin"] > store.snapshot(now=day)["melatonin"]
