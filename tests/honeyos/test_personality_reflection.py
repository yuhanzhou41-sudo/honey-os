from __future__ import annotations

from datetime import datetime, timedelta, timezone

from honeyos.companion.personality_candidates import PersonalityCandidateStore
from honeyos.companion.personality_reflection import (
    PersonalityReflectionRunner,
    ReflectionPolicy,
)


def _clock(value):
    return lambda: value


def _capture(store, count, *, observed_at):
    ids = []
    for i in range(count):
        ids.append(
            store.capture_observation(
                session_id="s",
                observed_at=observed_at.isoformat(),
                signal_flags=["preference"],
                assistant_excerpt=f"I prefer option {i}.",
            )
        )
    return ids


def test_count_trigger_runs_one_batch(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    ids = _capture(store, 20, observed_at=now)

    calls = []

    def adapter(payload):
        calls.append(payload)
        return {
            "operations": [
                {
                    "action": "create",
                    "target_layer": "relational_self",
                    "trait_key": "independent_preference",
                    "statement": "Tends to express genuine preferences.",
                    "confidence": 0.7,
                    "evidence_observation_ids": ids[:3],
                }
            ]
        }

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=adapter,
        now_fn=_clock(now),
    )

    result = runner.run_once()

    assert result.status == "success"
    assert len(calls) == 1
    assert store.pending_observation_count() == 0
    candidates = store.list_candidates(status="candidate")
    assert len(candidates) == 1
    assert candidates[0].trait_key == "independent_preference"


def test_below_threshold_makes_no_adapter_call(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 4, observed_at=now)

    called = False

    def adapter(payload):
        nonlocal called
        called = True
        return {"operations": []}

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=adapter,
        now_fn=_clock(now),
    )

    result = runner.run_once()

    assert result.status == "skipped"
    assert result.error == "below_threshold"
    assert called is False
    assert store.pending_observation_count() == 4


def test_age_trigger_requires_minimum_count(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    old = now - timedelta(hours=25)
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 5, observed_at=old)

    calls = []

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: calls.append(payload) or {"operations": []},
        now_fn=_clock(now),
    )
    result = runner.run_once()

    assert result.status == "success"
    assert len(calls) == 1
    assert store.pending_observation_count() == 0


def test_rate_limit_blocks_automatic_second_batch(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 20, observed_at=now)

    calls = []
    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: calls.append(payload) or {"operations": []},
        now_fn=_clock(now),
    )
    first = runner.run_once()
    assert first.status == "success"

    _capture(store, 20, observed_at=now + timedelta(hours=1))
    second = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: calls.append(payload) or {"operations": []},
        now_fn=_clock(now + timedelta(hours=1)),
    ).run_once()

    assert second.status == "skipped"
    assert second.error == "rate_limited"
    assert len(calls) == 1


def test_invalid_json_is_atomic_and_keeps_pending(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 20, observed_at=now)

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: "{bad json",
        now_fn=_clock(now),
    )
    result = runner.run_once()

    assert result.status == "failed"
    assert store.pending_observation_count() == 20
    assert store.list_candidates() == []


def test_invalid_operation_is_atomic_and_keeps_pending(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    ids = _capture(store, 20, observed_at=now)

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: {
            "operations": [
                {
                    "action": "create",
                    "target_layer": "relational_self",
                    "trait_key": "name",
                    "statement": "Should be rejected.",
                    "confidence": 0.9,
                    "evidence_observation_ids": [ids[0]],
                }
            ]
        },
        now_fn=_clock(now),
    )
    result = runner.run_once()

    assert result.status == "failed"
    assert store.pending_observation_count() == 20
    assert store.list_candidates() == []


def test_out_of_batch_evidence_is_rejected(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 20, observed_at=now)

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: {
            "operations": [
                {
                    "action": "create",
                    "target_layer": "relational_self",
                    "trait_key": "curiosity",
                    "statement": "Shows recurring curiosity.",
                    "confidence": 0.6,
                    "evidence_observation_ids": ["not-in-batch"],
                }
            ]
        },
        now_fn=_clock(now),
    )

    result = runner.run_once()

    assert result.status == "failed"
    assert store.pending_observation_count() == 20


def test_support_requires_existing_candidate(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    ids = _capture(store, 20, observed_at=now)

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: {
            "operations": [
                {
                    "action": "support",
                    "target_layer": "relational_self",
                    "trait_key": "curiosity",
                    "statement": "Shows recurring curiosity.",
                    "confidence": 0.6,
                    "evidence_observation_ids": [ids[0]],
                }
            ]
        },
        now_fn=_clock(now),
    )

    result = runner.run_once()

    assert result.status == "failed"
    assert store.list_candidates() == []
    assert store.pending_observation_count() == 20


def test_force_can_run_small_pending_batch(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 2, observed_at=now)

    calls = []
    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: calls.append(payload) or {"operations": []},
        now_fn=_clock(now),
    )

    result = runner.run_once(force=True)

    assert result.status == "success"
    assert len(calls) == 1
    assert store.pending_observation_count() == 0


def test_multi_operation_business_failure_is_atomic(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    ids = _capture(store, 20, observed_at=now)

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: {
            "operations": [
                {
                    "action": "create",
                    "target_layer": "relational_self",
                    "trait_key": "independent_preference",
                    "statement": "Tends to express genuine preferences.",
                    "confidence": 0.7,
                    "evidence_observation_ids": [ids[0]],
                },
                {
                    "action": "support",
                    "target_layer": "relational_self",
                    "trait_key": "missing_trait",
                    "statement": "This candidate does not exist.",
                    "confidence": 0.6,
                    "evidence_observation_ids": [ids[1]],
                },
            ]
        },
        now_fn=_clock(now),
    )

    result = runner.run_once()

    assert result.status == "failed"
    assert store.list_candidates() == []
    assert store.pending_observation_count() == 20


def test_create_existing_active_candidate_is_rejected_without_mutation(tmp_path):
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    store = PersonalityCandidateStore(tmp_path)
    existing = store.create_candidate(
        target_layer="relational_self",
        trait_key="curiosity",
        statement="Shows recurring curiosity.",
        confidence=0.5,
    )
    ids = _capture(store, 20, observed_at=now)

    runner = PersonalityReflectionRunner(
        tmp_path,
        adapter=lambda payload: {
            "operations": [
                {
                    "action": "create",
                    "target_layer": "relational_self",
                    "trait_key": "curiosity",
                    "statement": "Still curious.",
                    "confidence": 0.8,
                    "evidence_observation_ids": [ids[0]],
                }
            ]
        },
        now_fn=_clock(now),
    )

    before = store.get_candidate(existing.candidate_id)
    result = runner.run_once()
    after = store.get_candidate(existing.candidate_id)

    assert result.status == "failed"
    assert after == before
    assert store.pending_observation_count() == 20
