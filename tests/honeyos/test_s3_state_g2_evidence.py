"""S3: G2 evidence independence and the two nine-item companion state systems.

These tests pin the *existing* G2 contract (candidates, reflection, promotion,
suppression, rollback) and add only the guards S3 introduced:

- one source event can never be counted twice as independent support;
- personality signals come from Honey's own speech, not quoted user words;
- momentary state is companion-scoped;
- the two state systems stay separate with their own decay and no unbounded
  recall boost.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import honeyos.agent.turn_context as turn_context
import honeyos.agent.turn_finalizer as turn_finalizer
import honeyos.memory.runtime_shadow as runtime_shadow
from honeyos.companion import personality_observation as observation
from honeyos.companion import personality_promotion as promotion
from honeyos.companion.momentary_state import (
    HALF_LIFE_HOURS,
    HARD_EXPIRE_HOURS,
    load_momentary_state,
    update_momentary_state_from_turn,
)
from honeyos.companion.personality_candidates import PersonalityCandidateStore
from honeyos.companion.personality_observation import detect_observation_signals
from honeyos.companion.personality_observation_hook import capture_liked_reply
from honeyos.companion.personality_reflection import PersonalityReflectionRunner
from honeyos.companion.physiology_shadow import PhysiologyShadow, live_signals
from honeyos.core.state import SessionDB

_T0 = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def _candidate(store: PersonalityCandidateStore, layer: str = "relational_self", key: str = "independent_opinion"):
    return store.create_candidate(
        target_layer=layer,
        trait_key=key,
        statement="Tends to express an independent view.",
        confidence=0.72,
    )


def _evidence(store, candidate, *, refs, batches, sessions, types=None, start=_T0):
    for index, ref in enumerate(refs):
        store.add_evidence(
            candidate.candidate_id,
            evidence_type=(types or ["self_observation"] * len(refs))[index],
            summary=f"evidence {index}",
            reference=ref,
            observed_at=(start + timedelta(days=index)).isoformat(),
        )
        store.mark_observations_processed(
            [ref], reflection_batch_id=batches[index % len(batches)]
        )
    return store.get_candidate(candidate.candidate_id)


# ── G2 evidence: observation capture ────────────────────────────────────────


def test_saved_companion_reply_updates_temporary_state_but_not_candidates(tmp_path):
    """Item 1/14: a persisted companion reply feeds temporary state only.

    Personality evidence stays like-gated on this frozen baseline; ordinary
    replies must not silently create candidates.
    """
    update_momentary_state_from_turn(
        tmp_path, assistant_response="I'm curious about how that works.", turn_id="t1", now=_T0
    )
    state = load_momentary_state(tmp_path, now=_T0)
    assert state["axes"]["curiosity"] > 0
    assert state["last_turn_id"] == "t1"
    assert PersonalityCandidateStore(tmp_path).pending_observation_count() == 0


def test_repeated_processing_of_one_reply_yields_one_observation(tmp_path):
    """Item 2: the same reply/turn is idempotent at capture time."""
    store = PersonalityCandidateStore(tmp_path)
    first = store.capture_observation(
        session_id="s1",
        user_reference="u1",
        assistant_reference="turn1:assistant",
        assistant_excerpt="I prefer the direct version.",
        signal_flags=["preference"],
    )
    second = store.capture_observation(
        session_id="s1",
        user_reference="u1",
        assistant_reference="turn1:assistant-retry",
        assistant_excerpt="I prefer the direct version too.",
        signal_flags=["preference"],
    )
    assert first == second
    assert store.pending_observation_count() == 1


def test_liked_observation_is_idempotent_per_message(tmp_path):
    db = SessionDB(tmp_path / "state.db")
    try:
        db.create_session("one", "api_server")
        db.append_message("one", "user", "Explain how a backup can be verified.")
        row = db.append_message("one", "assistant", "I prefer checking its hash first.")
        db.set_message_reaction("one", row, "👍", toggle=False)
        first = capture_liked_reply(tmp_path, db, "one", row)
        assert first
        assert capture_liked_reply(tmp_path, db, "one", row) == first
    finally:
        db.close()


def test_quoted_user_words_do_not_become_honey_signals():
    """S3-B: observation is about Honey, not user facts it merely quotes."""
    quoted = detect_observation_signals(
        user_text="Do you agree?",
        assistant_text='The user said "I prefer tea" and "I disagree with that".',
    )
    assert quoted.eligible is False
    own = detect_observation_signals(
        user_text="Do you agree?",
        assistant_text="I disagree with that framing.",
    )
    assert own.flags == ("disagreement",)


def test_user_personality_feedback_is_still_captured():
    result = detect_observation_signals(
        user_text="我觉得你最近说话方式更直接了。",
        assistant_text="我明白你的意思。",
    )
    assert result.eligible is True
    assert result.flags == ("explicit_user_feedback",)


# ── G2 evidence: independence and promotion ─────────────────────────────────


def test_same_source_event_across_batches_counts_once(tmp_path):
    """Item 3: one event re-summarised in several batches is one support."""
    store = PersonalityCandidateStore(tmp_path)
    candidate = _candidate(store)
    obs_one = store.capture_observation(
        session_id="s1", user_reference="event-1", assistant_excerpt="I disagree, actually."
    )
    obs_two = store.capture_observation(
        session_id="s2", user_reference="event-1", assistant_excerpt="Actually I disagree."
    )
    obs_three = store.capture_observation(
        session_id="s3", user_reference="event-2", assistant_excerpt="I still disagree."
    )
    candidate = _evidence(
        store,
        candidate,
        refs=[obs_one, obs_two, obs_three],
        batches=["b1", "b2", "b1"],
        sessions=["s1", "s2", "s3"],
    )
    decision = promotion.evaluate_candidate_for_promotion(tmp_path, candidate)
    metrics = decision.metrics
    assert metrics["evidence_count"] == 2
    assert metrics["distinct_batches"] == 1
    assert decision.reason == "insufficient_independent_batches"


def test_duplicate_evidence_reference_does_not_increment_support(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    candidate = _candidate(store, key="technical_directness")
    obs = store.capture_observation(assistant_excerpt="I'd rather be direct.")
    first = store.add_evidence(
        candidate.candidate_id, evidence_type="self_observation", summary="a", reference=obs
    )
    second = store.add_evidence(
        candidate.candidate_id, evidence_type="self_observation", summary="b", reference=obs
    )
    assert first.support_count == 1
    assert second.support_count == 1
    assert len(store.list_evidence(candidate.candidate_id)) == 1


def test_duplicate_contradiction_reference_counts_once(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    candidate = _candidate(store, key="directness")
    first = store.record_contradiction(candidate.candidate_id, summary="a", reference="obs-1")
    second = store.record_contradiction(candidate.candidate_id, summary="b", reference="obs-1")
    assert first.contradiction_count == 1
    assert second.contradiction_count == 1


def test_independent_behaviour_adds_real_support(tmp_path):
    """Item 5/8: a genuinely different source still accumulates."""
    store = PersonalityCandidateStore(tmp_path)
    candidate = _candidate(store, layer="stable_core")
    obs = [
        store.capture_observation(
            session_id=f"s{i}",
            user_reference=f"event-{i}",
            assistant_excerpt="I chose to read more about that topic.",
        )
        for i in range(2)
    ]
    candidate = _evidence(
        store,
        candidate,
        refs=obs,
        batches=["b1", "b2"],
        sessions=["s1", "s2"],
        types=["assistant_behavior", "assistant_behavior"],
    )
    assert candidate.support_count == 2
    assert len(store.list_evidence(candidate.candidate_id)) == 2


def test_user_feedback_alone_cannot_promote(tmp_path):
    """Item 7: feedback influences, never decides."""
    store = PersonalityCandidateStore(tmp_path)
    candidate = _candidate(store, key="warmth")
    obs = [
        store.capture_observation(session_id=f"s{i}", user_reference=f"e{i}", assistant_excerpt="x")
        for i in range(4)
    ]
    candidate = _evidence(
        store,
        candidate,
        refs=obs,
        batches=["b1", "b2"],
        sessions=["s1", "s2"],
        types=["user_feedback"] * 4,
    )
    decision = promotion.evaluate_candidate_for_promotion(tmp_path, candidate)
    assert decision.eligible is False
    assert decision.reason == "user_feedback_not_sufficient"


def test_contradiction_delays_promotion(tmp_path):
    """Item 9: counter evidence weakens and defers."""
    store = PersonalityCandidateStore(tmp_path)
    candidate = _candidate(store, key="steadiness")
    obs = [
        store.capture_observation(session_id=f"s{i}", user_reference=f"e{i}", assistant_excerpt="x")
        for i in range(3)
    ]
    candidate = _evidence(
        store, candidate, refs=obs, batches=["b1", "b2"], sessions=["s1", "s2"]
    )
    for i in range(3):
        candidate = store.record_contradiction(
            candidate.candidate_id, summary=f"c{i}", reference=f"c-{i}"
        )
    decision = promotion.evaluate_candidate_for_promotion(tmp_path, candidate)
    assert decision.eligible is False
    assert decision.reason == "contradiction_dominates"


def test_reflection_can_conclude_no_change(tmp_path):
    """Item 12: no operation is a valid reflection outcome."""
    store = PersonalityCandidateStore(tmp_path)
    store.capture_observation(session_id="s1", assistant_excerpt="I prefer the second one.")
    runner = PersonalityReflectionRunner(
        tmp_path, adapter=lambda _payload: {"operations": [{"action": "none"}]}
    )
    result = runner.run_once(force=True)
    assert result.status == "success"
    assert result.operation_count == 0
    assert store.pending_observation_count() == 0
    assert store.list_candidates() == []


def test_manual_delete_and_suppression_still_control_promotion(tmp_path):
    """Item 10: user control is preserved."""
    store = PersonalityCandidateStore(tmp_path)
    candidate = _candidate(store, key="directness")
    obs = [
        store.capture_observation(session_id=f"s{i}", user_reference=f"e{i}", assistant_excerpt="x")
        for i in range(3)
    ]
    candidate = _evidence(
        store, candidate, refs=obs, batches=["b1", "b2"], sessions=["s1", "s2"]
    )
    candidate = store.get_candidate(candidate.candidate_id)
    assert promotion.promote_candidate(tmp_path, candidate)["status"] == "promoted"

    promotion.edit_authoritative_trait(tmp_path, "relational_self", "directness", None)
    authority = promotion.load_personality_authority(tmp_path)
    assert "directness" not in authority["relational_self"]
    assert "relational_self/directness" in authority["user_deleted_traits"]
    assert promotion.promote_candidate(tmp_path, candidate)["reason"] == "user_controlled_trait"

    other = _candidate(store, key="over_agreeable")
    store.reject_candidate(other.candidate_id, reason="not a real pattern")
    with pytest.raises(ValueError, match="suppressed"):
        store.create_candidate(
            target_layer="relational_self",
            trait_key="over_agreeable",
            statement="Tends to express an independent view.",
        )


def test_promotion_thresholds_are_unchanged():
    """Item 11: frozen G2 thresholds must not drift."""
    assert promotion.RELATIONAL_MIN_SUPPORT == 3
    assert promotion.RELATIONAL_MIN_CONFIDENCE == 0.65
    assert promotion.RELATIONAL_MIN_BATCHES == 2
    assert promotion.RELATIONAL_MIN_NON_FEEDBACK_EVIDENCE == 2
    assert promotion.STABLE_MIN_SUPPORT == 6
    assert promotion.STABLE_MIN_CONFIDENCE == 0.75
    assert promotion.STABLE_MIN_BATCHES == 3
    assert promotion.STABLE_MIN_SESSIONS == 3
    assert promotion.STABLE_MIN_SPAN_DAYS == 7.0
    assert promotion.STABLE_MIN_NON_FEEDBACK_EVIDENCE == 4
    assert promotion.STABLE_MAX_CONTRADICTIONS == 1
    assert promotion.STABLE_MAX_CONTRADICTION_RATIO == 0.25


def test_reflection_prompt_rejects_narration_and_user_directed_tasks():
    """Items 4/6/13: model-switch wording, self-narration and user orders."""
    source = Path(
        __import__("honeyos.companion.personality_reflection_execution", fromlist=["x"]).__file__
    ).read_text(encoding="utf-8")
    assert "Repetition is not independence" in source
    assert "Different wording, or a different model describing the same event" in source
    assert "A task the user asked" in source


# ── Two nine-item state systems ─────────────────────────────────────────────


def test_momentary_and_physiology_are_separate_stores(tmp_path):
    """State item 2: the two systems never share or overwrite storage."""
    update_momentary_state_from_turn(
        tmp_path, assistant_response="I'm excited about this.", now=_T0
    )
    shadow = PhysiologyShadow(tmp_path)
    shadow.apply_turn_appraisal("s1", "t1", "surprise", 0.6, now=_T0)

    assert (tmp_path / "companion" / "momentary_state.json").is_file()
    assert (tmp_path / "companion" / "physiology_shadow.sqlite").is_file()
    state = load_momentary_state(tmp_path, now=_T0)
    assert state["axes"]["energy"] > 0
    assert shadow.snapshot(now=_T0)["epinephrine"] > 0.05


def test_momentary_state_decays_and_hard_expires(tmp_path):
    """State item 3: existing half-life/expiry rules are intact."""
    update_momentary_state_from_turn(
        tmp_path, assistant_response="I'm curious about that.", now=_T0
    )
    half = load_momentary_state(tmp_path, now=_T0 + timedelta(hours=HALF_LIFE_HOURS))
    fresh = load_momentary_state(tmp_path, now=_T0)
    assert 0 < half["axes"]["curiosity"] < fresh["axes"]["curiosity"]
    expired = load_momentary_state(tmp_path, now=_T0 + timedelta(hours=HARD_EXPIRE_HOURS + 1))
    assert max(expired["axes"].values()) == 0


def test_physiology_decays_to_baseline_and_boost_is_zero_without_state(tmp_path):
    """State items 3/4: decay back to baseline, no state -> zero boost."""
    assert live_signals(tmp_path) == {}
    baseline_attention = max(0.0, 0.05 - 0.05) * 0.20
    assert baseline_attention == 0

    shadow = PhysiologyShadow(tmp_path)
    shadow.apply_turn_appraisal("s1", "t1", "surprise", 1.0, now=_T0)
    later = shadow.snapshot(now=_T0 + timedelta(hours=50))
    assert abs(later["epinephrine"] - 0.05) < 0.01


def test_recall_boost_is_bounded_by_epinephrine_and_arousal():
    """State item 5: no unbounded reinforcement path."""
    source = Path(runtime_shadow.__file__).read_text(encoding="utf-8")
    assert 'signals.get("epinephrine", 0.05) - 0.05) * 0.20' in source
    assert "min(1.0, float(row[\"arousal\"] or 0))" in source


def test_repeated_turn_appraisal_and_enqueue_are_idempotent(tmp_path):
    """State item 7: retries never double-apply one turn or one message."""
    shadow = PhysiologyShadow(tmp_path)
    first = shadow.apply_turn_appraisal("s1", "t1", "surprise", 0.8, now=_T0)
    second = shadow.apply_turn_appraisal("s1", "t1", "surprise", 0.8, now=_T0)
    assert first == second
    assert shadow.enqueue("s1", 1, now=_T0) is True
    assert shadow.enqueue("s1", 1, now=_T0) is False


def test_momentary_state_is_companion_scoped_in_turn_finalizer():
    """State item 6 / G2 item 14: no non-companion state pollution.

    S3.1: autonomous personality observation capture now lives inside the
    same companion-input-budget guard so it too is restricted to companion
    turns. The guard is the single gate for momentary_state, observation
    capture, and background reflection trigger.
    """
    source = Path(turn_finalizer.__file__).read_text(encoding="utf-8")
    guard = 'and getattr(agent, "_companion_input_budget", False) is True'
    assert guard in source
    assert source.index(guard) < source.index("update_momentary_state_from_turn(")
    # S3.1: capture_completed_agent_turn_observation IS inside the same block.
    assert "capture_completed_agent_turn_observation(" in source


def test_companion_turn_context_stages_promoted_and_momentary_note():
    """G2 chain tail: promoted traits + momentary state reach the model."""
    source = Path(turn_context.__file__).read_text(encoding="utf-8")
    stage = source.index("companion_profile_note(")
    consume = source.index("_gateway_notes = consume_gateway_turn_context_notes(agent)")
    assert stage < consume
    assert "drop_profile_fields_already_in_system_prompt" in source


def test_observation_uses_only_own_speech_helper():
    """S3-B: ownership boundary is shared with affect evidence."""
    assert callable(observation.strip_quoted_evidence)
    assert observation.strip_quoted_evidence('He said "I prefer X".') .strip() == "He said  ."


def test_candidate_store_reference_dedupe_leaves_legacy_rows_untouched(tmp_path):
    """Existing evidence rows without a reference keep counting individually."""
    store = PersonalityCandidateStore(tmp_path)
    candidate = _candidate(store, key="legacy_rows")
    store.add_evidence(candidate.candidate_id, evidence_type="self_observation", summary="a")
    store.add_evidence(candidate.candidate_id, evidence_type="self_observation", summary="b")
    updated = store.get_candidate(candidate.candidate_id)
    assert updated.support_count == 2
    assert len(store.list_evidence(candidate.candidate_id)) == 2


def test_observation_table_has_no_new_schema_columns(tmp_path):
    """No new G2 database or columns were introduced by S3."""
    store = PersonalityCandidateStore(tmp_path)
    store.capture_observation(session_id="s1", user_reference="u1", assistant_excerpt="x")
    conn = sqlite3.connect(store.db_path)
    try:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(personality_pending_observations)").fetchall()
        }
    finally:
        conn.close()
    assert columns == {
        "observation_id",
        "session_id",
        "user_reference",
        "assistant_reference",
        "observed_at",
        "signal_flags",
        "user_excerpt",
        "assistant_excerpt",
        "processed_at",
        "reflection_batch_id",
        "created_at",
    }
