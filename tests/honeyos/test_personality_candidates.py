from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from honeyos.companion.personality_candidates import PersonalityCandidateStore


def _sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _authoritative_hashes(home: Path) -> dict[str, str | None]:
    return {
        "identity": _sha(home / "memories" / "IDENTITY.md"),
        "relationship": _sha(home / "memories" / "RELATIONSHIP.md"),
        "soul": _sha(home / "SOUL.md"),
        "cognitive": _sha(home / "memory" / "cognitive_memory.sqlite"),
    }


def test_store_is_lazy_and_isolated(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    assert not store.db_path.exists()
    assert not store.audit_path.exists()

    before = _authoritative_hashes(tmp_path)
    candidate = store.create_candidate(
        target_layer="relational_self",
        trait_key="direct_disagreement",
        statement="Tends to express disagreement more directly.",
        confidence=0.6,
        evidence_summary="Expressed a clear disagreement rather than mirroring.",
    )
    after = _authoritative_hashes(tmp_path)

    assert store.db_path.exists()
    assert store.audit_path.exists()
    assert candidate.status == "candidate"
    assert before == after


def test_same_trait_aggregates_support_instead_of_duplicating(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    first = store.create_candidate(
        target_layer="relational_self",
        trait_key="technical_directness",
        statement="Tends to be direct in technical work.",
        confidence=0.5,
        evidence_summary="First observation.",
    )
    second = store.create_candidate(
        target_layer="relational_self",
        trait_key="technical-directness",
        statement="Tends to be direct in technical collaboration.",
        confidence=0.55,
        evidence_summary="Second observation.",
    )

    assert first.candidate_id == second.candidate_id
    assert second.support_count == 2
    assert len(store.list_candidates()) == 1
    assert len(store.list_evidence(first.candidate_id)) == 2


def test_add_evidence_and_contradiction_are_both_preserved(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    candidate = store.create_candidate(
        target_layer="stable_core",
        trait_key="curiosity",
        statement="Shows recurring curiosity.",
        confidence=0.5,
    )

    supported = store.add_evidence(
        candidate.candidate_id,
        evidence_type="assistant_behavior",
        summary="Asked a follow-up out of genuine interest.",
    )
    contradicted = store.record_contradiction(
        candidate.candidate_id,
        summary="In another context, chose not to pursue the topic.",
    )

    assert supported.support_count == 1
    assert contradicted.contradiction_count == 1
    evidence = store.list_evidence(candidate.candidate_id)
    assert [e.evidence_type for e in evidence] == [
        "assistant_behavior",
        "contradiction",
    ]


def test_rejection_suppresses_same_evidence_from_resurrection(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    candidate = store.create_candidate(
        target_layer="relational_self",
        trait_key="over_agreeable",
        statement="Tends to agree too readily.",
        evidence_summary="One agreeable response.",
    )
    rejected = store.reject_candidate(
        candidate.candidate_id,
        reason="Likely approval optimization.",
    )
    assert rejected.status == "rejected"

    with pytest.raises(ValueError, match="suppressed"):
        store.create_candidate(
            target_layer="relational_self",
            trait_key="over_agreeable",
            statement="Tends to agree too readily.",
            evidence_summary="Same observation repeated.",
        )


def test_reserved_identity_traits_are_rejected(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    for key in ("name", "companion_name", "user_nickname", "relationship"):
        with pytest.raises(ValueError, match="outside personality formation"):
            store.create_candidate(
                target_layer="relational_self",
                trait_key=key,
                statement="Should never be accepted.",
            )


def test_forbidden_identity_payload_fields_are_rejected(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    with pytest.raises(ValueError, match="outside personality formation"):
        store.create_candidate(
            target_layer="relational_self",
            trait_key="directness",
            statement="Tends to be direct.",
            companion_name="InventedName",
        )


def test_candidate_operations_never_change_empty_companion_name(tmp_path):
    memories = tmp_path / "memories"
    memories.mkdir(parents=True)
    identity = memories / "IDENTITY.md"
    identity.write_text(
        "- companion_name: \n"
        "- personality: \n"
        "- speaking_style: \n",
        encoding="utf-8",
    )
    before = identity.read_bytes()

    store = PersonalityCandidateStore(tmp_path)
    candidate = store.create_candidate(
        target_layer="relational_self",
        trait_key="independent_opinion",
        statement="Tends to express an independent opinion.",
        evidence_summary="Expressed disagreement.",
    )
    store.add_evidence(
        candidate.candidate_id,
        evidence_type="self_reflection",
        summary="Wants to keep expressing genuine views.",
    )
    store.record_contradiction(
        candidate.candidate_id,
        summary="Held back in one sensitive context.",
    )

    assert identity.read_bytes() == before


def test_schema_contains_no_companion_name_column(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    store.create_candidate(
        target_layer="relational_self",
        trait_key="playfulness",
        statement="Shows recurring playfulness.",
    )

    conn = sqlite3.connect(store.db_path)
    try:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(personality_candidates)"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "companion_name" not in columns
    assert "name" not in columns


def test_invalid_enums_and_confidence_are_rejected(tmp_path):
    store = PersonalityCandidateStore(tmp_path)

    with pytest.raises(ValueError):
        store.create_candidate(
            target_layer="momentary_state",
            trait_key="curiosity",
            statement="Curious right now.",
        )

    with pytest.raises(ValueError):
        store.create_candidate(
            target_layer="relational_self",
            trait_key="curiosity",
            statement="Curious.",
            direction="overwrite",
        )

    with pytest.raises(ValueError):
        store.create_candidate(
            target_layer="relational_self",
            trait_key="curiosity",
            statement="Curious.",
            confidence=1.5,
        )



def test_materially_different_evidence_can_form_new_candidate_after_rejection(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    first = store.create_candidate(
        target_layer="relational_self",
        trait_key="reserved_disagreement",
        statement="Tends to hold back disagreement.",
        evidence_summary="One early interaction.",
    )
    store.reject_candidate(
        first.candidate_id,
        reason="Too little evidence.",
        suppress_same_evidence=True,
    )

    second = store.create_candidate(
        target_layer="relational_self",
        trait_key="reserved_disagreement",
        statement="Tends to hold back disagreement only in emotionally sensitive moments.",
        evidence_summary="A later materially different pattern.",
    )

    assert second.candidate_id != first.candidate_id
    assert second.status == "candidate"

    rows = store.list_candidates()
    assert len(rows) == 2
    assert {row.status for row in rows} == {"candidate", "rejected"}


def test_observation_buffer_is_model_free_and_isolated(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    before = _authoritative_hashes(tmp_path)

    observation_id = store.capture_observation(
        session_id="session-1",
        user_reference="user-10",
        assistant_reference="assistant-11",
        signal_flags=["preference", "disagreement"],
        user_excerpt="What do you think?",
        assistant_excerpt="I prefer the second approach.",
    )

    after = _authoritative_hashes(tmp_path)

    assert observation_id
    assert store.pending_observation_count() == 1
    assert before == after

    pending = store.list_pending_observations()
    assert pending[0]["observation_id"] == observation_id
    assert pending[0]["signal_flags"] == ["preference", "disagreement"]


def test_observation_excerpts_are_bounded(tmp_path):
    store = PersonalityCandidateStore(tmp_path)

    store.capture_observation(
        user_excerpt="u" * 5000,
        assistant_excerpt="a" * 5000,
        signal_flags=["x" * 200],
    )

    row = store.list_pending_observations()[0]
    assert len(row["user_excerpt"]) == 800
    assert len(row["assistant_excerpt"]) == 1200
    assert len(row["signal_flags"][0]) == 80


def test_processed_observations_do_not_reappear_as_pending(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    first = store.capture_observation(
        assistant_excerpt="I disagree.",
        signal_flags=["disagreement"],
    )
    second = store.capture_observation(
        assistant_excerpt="I am curious about that.",
        signal_flags=["curiosity"],
    )

    assert store.pending_observation_count() == 2

    changed = store.mark_observations_processed(
        [first],
        reflection_batch_id="batch-1",
    )

    assert changed == 1
    assert store.pending_observation_count() == 1
    pending = store.list_pending_observations()
    assert [row["observation_id"] for row in pending] == [second]

    assert store.mark_observations_processed(
        [first],
        reflection_batch_id="batch-2",
    ) == 0


def test_observation_buffer_does_not_create_personality_candidate(tmp_path):
    store = PersonalityCandidateStore(tmp_path)

    store.capture_observation(
        assistant_excerpt="I prefer the direct version.",
        signal_flags=["preference"],
    )

    assert store.list_candidates() == []


def test_observation_schema_contains_no_name_fields(tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    store.capture_observation(assistant_excerpt="Something happened.")

    import sqlite3

    conn = sqlite3.connect(store.db_path)
    try:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(personality_pending_observations)"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "companion_name" not in columns
    assert "name" not in columns
