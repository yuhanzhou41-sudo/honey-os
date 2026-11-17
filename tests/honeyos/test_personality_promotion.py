
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from honeyos.companion.personality_candidates import PersonalityCandidateStore
from honeyos.companion.personality_promotion import (
    evaluate_candidate_for_promotion,
    load_personality_authority,
    personality_authority_note,
    promote_candidate,
    promote_eligible_candidates,
    rollback_authoritative_trait,
)


def _make_evidence(store, *, candidate, count, batches, sessions, start, evidence_type="self_observation"):
    ids = []
    for i in range(count):
        obs = store.capture_observation(
            session_id=sessions[i % len(sessions)],
            observed_at=(start + timedelta(days=i)).isoformat(),
            signal_flags=["preference"],
            assistant_excerpt=f"I prefer option {i}.",
        )
        ids.append(obs)
        store.add_evidence(
            candidate.candidate_id,
            evidence_type=evidence_type,
            summary=f"evidence {i}",
            reference=obs,
        )
    for i, obs in enumerate(ids):
        store.mark_observations_processed([obs], reflection_batch_id=batches[i % len(batches)])
    return ids


def test_immature_candidate_does_not_promote(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    c = store.create_candidate(
        target_layer="relational_self",
        trait_key="independent_opinion",
        statement="Tends to express an independent view.",
        confidence=0.7,
    )
    assert evaluate_candidate_for_promotion(tmp_path, c).eligible is False
    assert promote_candidate(tmp_path, c)["status"] == "deferred"


def test_mature_relational_candidate_promotes(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    c = store.create_candidate(
        target_layer="relational_self",
        trait_key="independent_opinion",
        statement="Tends to express an independent view.",
        confidence=0.72,
    )
    _make_evidence(
        store, candidate=c, count=3, batches=["b1", "b2"], sessions=["s1", "s2"],
        start=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    c = store.get_candidate(c.candidate_id)
    assert evaluate_candidate_for_promotion(tmp_path, c).eligible is True
    assert promote_candidate(tmp_path, c)["status"] == "promoted"
    assert "independent_opinion" in load_personality_authority(tmp_path)["relational_self"]
    assert "independent view" in personality_authority_note(tmp_path)
    authority = load_personality_authority(tmp_path)
    assert promote_eligible_candidates(tmp_path)["promoted_count"] == 0
    assert load_personality_authority(tmp_path) == authority

    _make_evidence(
        store, candidate=c, count=1, batches=["b3"], sessions=["s3"],
        start=datetime(2026, 9, 5, tzinfo=timezone.utc),
    )
    assert promote_eligible_candidates(tmp_path)["promoted_count"] == 1
    assert load_personality_authority(tmp_path)["relational_self"]["independent_opinion"][
        "support_count"
    ] == 4


def test_user_feedback_only_cannot_promote(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    c = store.create_candidate(
        target_layer="relational_self",
        trait_key="warmth",
        statement="Tends to respond warmly.",
        confidence=0.8,
    )
    _make_evidence(
        store, candidate=c, count=4, batches=["b1", "b2"], sessions=["s1", "s2"],
        start=datetime(2026, 9, 1, tzinfo=timezone.utc),
        evidence_type="user_feedback",
    )
    c = store.get_candidate(c.candidate_id)
    d = evaluate_candidate_for_promotion(tmp_path, c)
    assert d.eligible is False
    assert d.reason == "user_feedback_not_sufficient"


def test_rollback_blocks_same_candidate(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    c = store.create_candidate(
        target_layer="relational_self",
        trait_key="directness",
        statement="Tends to communicate directly.",
        confidence=0.8,
    )
    _make_evidence(
        store, candidate=c, count=3, batches=["b1", "b2"], sessions=["s1", "s2"],
        start=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    c = store.get_candidate(c.candidate_id)
    assert promote_candidate(tmp_path, c)["status"] == "promoted"
    assert rollback_authoritative_trait(
        tmp_path, target_layer="relational_self", trait_key="directness",
        reason="manual correction",
    )["status"] == "rolled_back"
    d = evaluate_candidate_for_promotion(tmp_path, c)
    assert d.eligible is False
    assert d.reason == "blocked_candidate"


def test_stable_core_requires_relational_authority_and_longer_span(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    stable = store.create_candidate(
        target_layer="stable_core",
        trait_key="independent_opinion",
        statement="Maintains an independent point of view.",
        confidence=0.82,
    )
    _make_evidence(
        store, candidate=stable, count=6, batches=["b1", "b2", "b3"],
        sessions=["s1", "s2", "s3"],
        start=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    stable = store.get_candidate(stable.candidate_id)
    assert evaluate_candidate_for_promotion(tmp_path, stable).reason == "requires_relational_authority"

    rel = store.create_candidate(
        target_layer="relational_self",
        trait_key="independent_opinion",
        statement="Tends to express an independent point of view.",
        confidence=0.75,
    )
    _make_evidence(
        store, candidate=rel, count=3, batches=["r1", "r2"], sessions=["s1", "s2"],
        start=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    rel = store.get_candidate(rel.candidate_id)
    assert promote_candidate(tmp_path, rel)["status"] == "promoted"

    extra = store.capture_observation(
        session_id="s3",
        observed_at=datetime(2026, 9, 12, tzinfo=timezone.utc).isoformat(),
        signal_flags=["self_reflection"],
        assistant_excerpt="I have noticed this pattern remains stable.",
    )
    store.add_evidence(
        stable.candidate_id,
        evidence_type="self_observation",
        summary="later confirmation",
        reference=extra,
    )
    store.mark_observations_processed([extra], reflection_batch_id="b4")
    stable = store.get_candidate(stable.candidate_id)
    assert evaluate_candidate_for_promotion(tmp_path, stable).eligible is True
    assert promote_candidate(tmp_path, stable)["status"] == "promoted"


def test_candidate_only_never_appears_in_authority_note(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    store.create_candidate(
        target_layer="relational_self",
        trait_key="private_candidate",
        statement="This should remain backstage.",
        confidence=0.9,
    )
    assert "This should remain backstage." not in personality_authority_note(tmp_path)
