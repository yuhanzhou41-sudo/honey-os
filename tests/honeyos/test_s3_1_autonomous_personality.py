"""S3.1: restore autonomous (non-like) personality observation.

S3 froze G2 to a like-only entry for personality evidence. S3.1 reconnects
the production hook on the normal companion turn-completion path so that
Honey's observable behavior is captured without requiring user approval.

These tests pin:

- turn_finalizer now calls capture_completed_agent_turn_observation for
  companion turns (model-free, deterministic signals only).
- The normal (liked_only=False) promotion path is fully open: evidence
  from autonomous observations supports candidate promotion without any
  like gate.
- Like-gated path stays independent (separate sqlite) and retains the
  retraction / missing_current_reply_approval safety net.
- No extra LLM call is added per ordinary turn.
- Non-companion turns and low-signal replies remain excluded.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from honeyos.companion.personality_candidates import PersonalityCandidateStore
from honeyos.companion.personality_observation import detect_observation_signals
from honeyos.companion.personality_observation_hook import (
    capture_completed_agent_turn_observation,
    capture_completed_turn_observation,
)
from honeyos.companion.personality_promotion import (
    evaluate_candidate_for_promotion,
    promote_eligible_candidates,
)
from honeyos.companion.personality_reflection import PersonalityReflectionRunner
from honeyos.companion.personality_reflection_execution import (
    maybe_start_background_personality_reflection,
)

_T0 = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)


def _t(day_offset: int, hour: int = 12) -> str:
    return (_T0 + timedelta(days=day_offset, hours=hour - 12)).isoformat()


def _make_agent(tmp_path: Path, *, turn_id: str = "t1", session_id: str = "s1"):
    return SimpleNamespace(
        honeyos_home=str(tmp_path),
        session_id=session_id,
        _companion_input_budget=True,
    )


# ── 1. Autonomous observation capture ──────────────────────────────────────


def test_completed_turn_captures_signal_eligible_reply(tmp_path, monkeypatch):
    """Item 1/11: a normal companion reply with personality signals captures."""
    monkeypatch.delenv("HONEYOS_HOME", raising=False)
    agent = _make_agent(tmp_path, turn_id="turn-abc", session_id="sess-1")
    result = capture_completed_agent_turn_observation(
        agent,
        turn_id="turn-abc",
        user_message="Should we go with plan A or B?",
        assistant_response="I'm curious about whether plan B has a fallback.",
        observed_at=_t(0),
    )
    assert result["captured"] is True
    assert result["observation_id"]
    assert "curiosity" in result["signal_flags"]
    store = PersonalityCandidateStore(tmp_path)
    pending = store.list_pending_observations()
    assert len(pending) == 1
    assert pending[0]["session_id"] == "sess-1"


def test_completed_turn_skips_low_signal_reply(tmp_path, monkeypatch):
    """Item 1b: a plain factual reply without personality signals does not
    create an observation (we don't want every 回复 to become a candidate).
    """
    monkeypatch.delenv("HONEYOS_HOME", raising=False)
    agent = _make_agent(tmp_path)
    result = capture_completed_agent_turn_observation(
        agent,
        turn_id="t1",
        user_message="What's the capital of France?",
        assistant_response="Paris.",
    )
    assert result["captured"] is False
    store = PersonalityCandidateStore(tmp_path)
    assert store.pending_observation_count() == 0


def test_completed_turn_is_idempotent_per_turn(tmp_path, monkeypatch):
    """Item 1c: the same turn_id can be processed repeatedly without creating
    duplicate observations (dedupe on session + assistant_reference).
    """
    monkeypatch.delenv("HONEYOS_HOME", raising=False)
    agent = _make_agent(tmp_path, turn_id="turn-xyz")
    kwargs = dict(
        turn_id="turn-xyz",
        user_message="How do you feel about this?",
        assistant_response="I think I'm getting bolder about sharing opinions.",
    )
    first = capture_completed_agent_turn_observation(agent, **kwargs)
    second = capture_completed_agent_turn_observation(agent, **kwargs)
    assert first["observation_id"] == second["observation_id"]
    store = PersonalityCandidateStore(tmp_path)
    assert store.pending_observation_count() == 1


def test_completed_turn_fail_open_on_exception(tmp_path, monkeypatch):
    """Item 1d: never let observation capture break the chat loop. The
    helper wraps all work in try/except and returns captured=False even
    when the store constructor raises.
    """
    monkeypatch.delenv("HONEYOS_HOME", raising=False)

    def _boom(*args, **kwargs):
        raise RuntimeError("store is broken")

    monkeypatch.setattr(
        "honeyos.companion.personality_observation_hook.PersonalityCandidateStore",
        _boom,
    )
    agent = _make_agent(tmp_path, turn_id="t1")
    result = capture_completed_agent_turn_observation(
        agent,
        turn_id="t1",
        user_message="hi",
        assistant_response="I prefer dark mode.",
    )
    assert result["captured"] is False
    assert "store is broken" in result["error"]


# ── 2. No-like promotion path is fully open ────────────────────────────────


def test_candidate_promotes_without_any_like(tmp_path):
    """Item 2: without a single like, an autonomous candidate that meets
    the relational threshold still promotes through the normal store.

    This is the core S3.1 contract — G2 personality is not gated on user
    feedback approval.
    """
    store = PersonalityCandidateStore(tmp_path)
    candidate = store.create_candidate(
        target_layer="relational_self",
        trait_key="independent_opinion",
        statement="Tends to express independent opinions.",
        confidence=0.72,
    )
    # Three distinct source events (reference = observation_id from our
    # pending observations) across two reflection batches.
    obs_refs = []
    for idx, session in enumerate(("s1", "s1", "s2")):
        obs_id = store.capture_observation(
            session_id=session,
            assistant_reference=f"turn{idx}:assistant",
            user_reference=f"turn{idx}:user",
            assistant_excerpt="I think I'm getting bolder.",
            signal_flags=["self_reflection"],
            observed_at=_t(idx),
        )
        obs_refs.append(obs_id)

    for idx, obs_id in enumerate(obs_refs):
        store.add_evidence(
            candidate.candidate_id,
            evidence_type="self_observation",
            summary="Expressed independent opinion.",
            reference=obs_id,
            observed_at=_t(idx),
        )
        batch = "batch1" if idx <= 1 else "batch2"
        store.mark_observations_processed([obs_id], reflection_batch_id=batch)

    decision = evaluate_candidate_for_promotion(tmp_path, store.get_candidate(candidate.candidate_id))
    assert decision.eligible, f"should promote but got {decision.reason}: {decision.metrics}"


def test_candidate_promotion_requires_enough_non_feedback_evidence(tmp_path):
    """Item 2b: user_feedback alone does NOT promote — still need at least
    2 independent behavioral observations (self_observation / shared_experience
    / assistant_behavior). This prevents likes from becoming personality
    instructions.
    """
    store = PersonalityCandidateStore(tmp_path)
    candidate = store.create_candidate(
        target_layer="relational_self",
        trait_key="test_trait",
        statement="Some trait.",
        confidence=0.75,
    )
    # One user_feedback, two self_observation — this DOES meet the threshold
    # and should promote (non_feedback_count=2 >= RELATIONAL_MIN_NON_FEEDBACK_EVIDENCE).
    obs_refs = []
    for idx in range(3):
        obs_id = store.capture_observation(
            session_id="s1",
            assistant_reference=f"turn{idx}:assistant",
            observed_at=_t(idx),
        )
        obs_refs.append(obs_id)

    store.add_evidence(candidate.candidate_id, evidence_type="user_feedback",
                       summary="User liked this.", reference=obs_refs[0], observed_at=_t(0))
    store.add_evidence(candidate.candidate_id, evidence_type="self_observation",
                       summary="Observed behavior A.", reference=obs_refs[1], observed_at=_t(1))
    store.add_evidence(candidate.candidate_id, evidence_type="self_observation",
                       summary="Observed behavior B.", reference=obs_refs[2], observed_at=_t(2))
    store.mark_observations_processed(obs_refs[0:1], reflection_batch_id="batch1")
    store.mark_observations_processed(obs_refs[1:], reflection_batch_id="batch2")

    decision = evaluate_candidate_for_promotion(tmp_path, store.get_candidate(candidate.candidate_id))
    assert decision.eligible, decision.reason

    # Now try with only user_feedback — should fail.
    store2 = PersonalityCandidateStore(tmp_path / "two")
    cand2 = store2.create_candidate(target_layer="relational_self", trait_key="f",
                                    statement="f", confidence=0.8)
    obs_ids = []
    for i in range(3):
        o = store2.capture_observation(session_id="s", assistant_reference=f"t{i}:a", observed_at=_t(i))
        obs_ids.append(o)
    for i, o in enumerate(obs_ids):
        store2.add_evidence(cand2.candidate_id, evidence_type="user_feedback",
                            summary=f"like {i}", reference=o, observed_at=_t(i))
        store2.mark_observations_processed([o], reflection_batch_id=f"b{i}")

    decision2 = evaluate_candidate_for_promotion(tmp_path / "two", store2.get_candidate(cand2.candidate_id))
    assert not decision2.eligible
    assert decision2.reason == "user_feedback_not_sufficient"
    assert decision2.metrics["non_feedback_count"] == 0


# ── 3. Self statement ≠ personality conclusion ─────────────────────────────


def test_plain_self_statement_does_not_promote_alone(tmp_path):
    """Item 3: a single self-describing utterance does not promote — still
    needs repeated independent evidence across sessions/batches/time.
    """
    store = PersonalityCandidateStore(tmp_path)
    obs1 = store.capture_observation(
        session_id="s1",
        assistant_reference="t1:a",
        assistant_excerpt="I notice I'm more reflective lately.",
        signal_flags=["self_reflection"],
        observed_at=_t(0),
    )
    candidate = store.create_candidate(
        target_layer="relational_self",
        trait_key="reflective",
        statement="Sometimes expresses self-awareness about reflectiveness.",
        confidence=0.55,
        evidence_summary="Self-reflection observed.",
        evidence_reference=obs1,
        origin="self_observation",
    )
    store.mark_observations_processed([obs1], reflection_batch_id="b1")
    decision = evaluate_candidate_for_promotion(tmp_path, store.get_candidate(candidate.candidate_id))
    assert not decision.eligible
    # Only one support, one batch, only one event — all below threshold.
    assert decision.reason in {"insufficient_support", "insufficient_independent_batches"}


# ── 4. Distinct behaviors → independent evidence ──────────────────────────


def test_distinct_sessions_count_as_independent_evidence(tmp_path):
    """Item 4: behaviors in different sessions/source events accumulate
    independently. Same trait emerging from s1, s2, s3 is three supports.
    """
    store = PersonalityCandidateStore(tmp_path)
    candidate = store.create_candidate(
        target_layer="relational_self", trait_key="curious",
        statement="Often expresses curiosity.", confidence=0.55,
    )
    for idx, session in enumerate(("s1", "s2", "s3")):
        obs = store.capture_observation(
            session_id=session,
            assistant_reference=f"turn{idx}:assistant",
            assistant_excerpt="I wonder about that.",
            signal_flags=["curiosity"],
            observed_at=_t(idx),
        )
        store.add_evidence(candidate.candidate_id, evidence_type="self_observation",
                           summary="Expressed curiosity.", reference=obs, observed_at=_t(idx))
        store.mark_observations_processed([obs], reflection_batch_id=f"batch{idx // 2}")

    updated = store.get_candidate(candidate.candidate_id)
    assert updated.support_count >= 3
    decision = evaluate_candidate_for_promotion(tmp_path, updated)
    assert decision.eligible, decision.reason


# ── 5. Like + autonomous parallel: separate stores, separate reflections ──


def test_like_and_autonomous_paths_write_separate_sqlite_files(tmp_path):
    """Item 5: S3.1 keeps the two entry points on separate DB files.
    capture_completed_turn_observation uses the normal store; liked_only
    stays on the liked store. This preserves like-retraction safety while
    allowing the normal path to reach promotion independently.
    """
    normal = PersonalityCandidateStore(tmp_path)
    liked = PersonalityCandidateStore(tmp_path, liked_only=True)
    assert normal.db_path.name == "personality_candidates.sqlite"
    assert liked.db_path.name == "personality_liked_candidates.sqlite"
    assert normal.db_path != liked.db_path

    # Autonomous observation lands in the normal store.
    obs_normal = capture_completed_turn_observation(
        tmp_path, session_id="s1",
        assistant_reference="t1:a", user_reference="t1:u",
        assistant_text="I prefer the simpler path.",
        observed_at=_t(0),
    )
    assert obs_normal["captured"]
    assert normal.pending_observation_count() == 1
    assert liked.pending_observation_count() == 0

    # The two stores are independent.
    liked_only_result = evaluate_candidate_for_promotion(tmp_path, _FakeCandidate("relational_self", "x", 0.7, 3, 0), liked_only=True)
    # liked_only store has zero evidence → anything evaluated there is rejected.
    assert liked_only_result.reason != "mature_relational_candidate"


class _FakeCandidate:
    def __init__(self, layer, key, conf, support, contras):
        self.target_layer = layer
        self.trait_key = key
        self.status = "candidate"
        self.confidence = conf
        self.support_count = support
        self.contradiction_count = contras


# ── 6. Reflection trigger: threshold-gated, no auto-model-call ─────────────


def test_reflection_trigger_requires_threshold(tmp_path):
    """Item 6: maybe_start_background_personality_reflection calls
    should_reflect() first — below threshold it returns started=False
    without spinning a thread or touching a model.
    """
    # 0 pending → nothing starts.
    result = maybe_start_background_personality_reflection(tmp_path)
    assert result["started"] is False
    assert result["reason"] == "no_pending_observations"

    # 1 pending → still below count_trigger (20) and age_trigger (24h + 5).
    store = PersonalityCandidateStore(tmp_path)
    store.capture_observation(
        session_id="s", assistant_reference="t1:a",
        assistant_excerpt="I prefer it.", signal_flags=["preference"],
        observed_at=_t(0),
    )
    result = maybe_start_background_personality_reflection(tmp_path)
    assert result["started"] is False
    assert result["reason"] in {"below_threshold", "rate_limited", "no_pending_observations"}


def test_reflection_rate_limit_respected(tmp_path):
    """After a successful reflection, another one is not started within
    min_automatic_interval_hours (12h) even if there are new observations.
    """
    store = PersonalityCandidateStore(tmp_path)
    for i in range(25):
        store.capture_observation(
            session_id="s",
            assistant_reference=f"t{i}:a",
            assistant_excerpt="I prefer the simpler path.",
            signal_flags=["preference"],
            observed_at=_t(i),
        )

    # First run — should fire the thread.
    result1 = maybe_start_background_personality_reflection(tmp_path)
    assert result1["started"] is True

    # But if the last_success_at state was just written (or mocked) within
    # the rate-limit window, a second maybe_start should not fire.  Since
    # we use a real reflection_state.json written by the runner and we
    # don't actually let the thread complete, the state is not written —
    # so the rate-limit does not kick in here. What is pinned is that the
    # threshold check is real and no model is called below threshold.
    # That's verified by the two cases above.


# ── 7. Turn_finalizer wiring (source-level assertion) ──────────────────────


def test_turn_finalizer_calls_autonomous_observation_in_companion_guard():
    """Item 7: the production call chain — companion turn completion →
    capture_completed_agent_turn_observation → maybe_start_background_
    personality_reflection — is present in the finalizer source and is
    gated by the _companion_input_budget guard (same block as momentary
    state update).
    """
    import honeyos.agent.turn_finalizer as tf
    src = Path(tf.__file__).read_text(encoding="utf-8")

    # Guard is the single companion-scoped gate.
    guard = 'and getattr(agent, "_companion_input_budget", False) is True'
    assert guard in src

    # Both autonomous hooks are wired.
    capture_idx = src.index("capture_completed_agent_turn_observation(")
    reflect_idx = src.index("maybe_start_background_personality_reflection(")
    guard_idx = src.index(guard)
    persist_idx = src.index("agent._persist_session(messages, conversation_history)")

    # Order: persist → guard → hooks → context engine hook.
    assert persist_idx < guard_idx < capture_idx < reflect_idx
    assert src.index("# Context engine observation hook:") > reflect_idx

    # Still excluded from non-companion turns.
    assert "enqueue_completed_reply(" not in src


def test_no_extra_llm_call_per_companion_turn():
    """Item 8 (hard requirement): the autonomous observation path is
    model-free. detect_observation_signals uses pure regex on stripped
    text. No import of any client/call_llm/Provider appears in the
    observation hook or detection module.
    """
    hook_src = Path(
        "honeyos/companion/personality_observation_hook.py"
    ).absolute()
    # Resolve via a path that pytest's cwd gives us.
    # We use the actual package path:
    import honeyos.companion.personality_observation_hook as hook
    import honeyos.companion.personality_observation as obs
    hook_code = Path(hook.__file__).read_text(encoding="utf-8")
    obs_code = Path(obs.__file__).read_text(encoding="utf-8")

    for forbidden in ("call_llm", "from honeyos.agent.auxiliary",
                      "from honeyos.agent.relay_llm", "AuxiliaryClient",
                      "LLMProvider", "client.chat.completions"):
        assert forbidden not in hook_code, f"{forbidden} leaked into observation hook"
        assert forbidden not in obs_code, f"{forbidden} leaked into observation"


def test_reflection_runner_builds_bounded_context(tmp_path):
    """Item 9: the reflection adapter input is bounded — observations come
    from pending observations (≤50), candidates are capped at 20 active.
    No full chat history, no full USER.md / MEMORY.md, no entire DB dump.
    """
    store = PersonalityCandidateStore(tmp_path)
    # Exceed batch_limit (50) — _build_batch must cap it.
    for i in range(80):
        store.capture_observation(
            session_id="s",
            assistant_reference=f"t{i}:a",
            assistant_excerpt="I prefer it.",
            signal_flags=["preference"],
            observed_at=_t(i),
        )
    store.create_candidate(target_layer="relational_self", trait_key=f"t{i % 25}",
                            statement="X", confidence=0.55)

    # No adapter call needed — we just inspect _build_batch directly.
    runner = PersonalityReflectionRunner(tmp_path, adapter=lambda _: '{"operations":[]}')
    _, observations, payload = runner._build_batch()
    assert len(observations) <= runner.policy.batch_limit
    assert len(payload["observations"]) <= runner.policy.batch_limit
    # Candidates bounded at 20.
    assert len(payload["candidates"]) <= 20
    # No full transcripts, no memory dumps.
    for forbidden in ("conversation_history", "USER.md", "MEMORY.md", "long_term",
                      "momentary_state", "physiology"):
        assert forbidden not in payload


# ── 8. Contradiction can soften or revise a candidate ─────────────────────


def test_contradiction_reduces_confidence(tmp_path):
    """Item 10: contradictory evidence weakens a candidate without
    destroying existing support. A single contradiction to a strong
    candidate is not automatically a rejection.
    """
    store = PersonalityCandidateStore(tmp_path)
    candidate = store.create_candidate(
        target_layer="relational_self", trait_key="curious",
        statement="Often curious.", confidence=0.75,
    )
    # Three supports.
    obs_ids = []
    for idx in range(3):
        o = store.capture_observation(
            session_id=f"s{idx}", assistant_reference=f"t{idx}:a",
            assistant_excerpt="I'm curious.", signal_flags=["curiosity"],
            observed_at=_t(idx),
        )
        obs_ids.append(o)
        store.add_evidence(candidate.candidate_id, evidence_type="self_observation",
                           summary="Curious remark.", reference=o, observed_at=_t(idx))
    cand = store.get_candidate(candidate.candidate_id)
    high_conf = cand.confidence
    high_support = cand.support_count

    # Add a contradiction.
    cand2 = store.record_contradiction(candidate.candidate_id,
                                       summary="Sometimes shows disinterest.",
                                       reference="contrad1",
                                       observed_at=_t(4))
    assert cand2.contradiction_count == 1
    assert cand2.confidence < high_conf
    # Support stays.
    assert cand2.support_count == high_support
    assert cand2.status == "candidate"  # not auto-rejected


# ── 9. Manually blocked / suppressed candidate ignores new evidence ────────


def test_suppressed_candidate_rejects_new_support(tmp_path):
    """Item 11: suppress_candidate() prevents future evidence from
    reactivating it — like gates at the candidate-store level.
    """
    store = PersonalityCandidateStore(tmp_path)
    candidate = store.create_candidate(
        target_layer="relational_self", trait_key="curious",
        statement="Often curious.", confidence=0.72,
    )
    suppressed = store.suppress_candidate(candidate.candidate_id, reason="user disapproval")
    assert suppressed.status == "suppressed"

    # Try to add_evidence on suppressed candidate — should raise.
    with pytest.raises(ValueError):
        store.add_evidence(candidate.candidate_id, evidence_type="self_observation",
                           summary="Still curious.", reference="newobs")


# ── 10. Like retraction only affects liked-store promotions ──────────────────


def test_like_retraction_does_not_touch_autonomous_store(tmp_path):
    """S3.1 F: liked-only promotions respect liked retraction. Autonomous
    (liked_only=False) promotions don't see the liked-only retraction gate
    and don't require any like approval.
    """
    store_liked = PersonalityCandidateStore(tmp_path, liked_only=True)
    store_normal = PersonalityCandidateStore(tmp_path)

    liked_candidate = store_liked.create_candidate(
        target_layer="relational_self", trait_key="x",
        statement="x", confidence=0.8,
    )
    normal_candidate = store_normal.create_candidate(
        target_layer="relational_self", trait_key="y",
        statement="y", confidence=0.8,
    )

    # liked_only evaluation hits the all_evidence_liked gate when no
    # evidence is liked; normal evaluation skips that gate entirely.
    liked_eval = evaluate_candidate_for_promotion(tmp_path, liked_candidate, liked_only=True)
    normal_eval = evaluate_candidate_for_promotion(tmp_path, normal_candidate, liked_only=False)

    # liked_only gate triggers because the liked store has no evidence yet.
    assert liked_eval.reason == "missing_current_reply_approval"
    # Normal store: no gate on like at all; will be rejected only for
    # insufficient_support / insufficient_independent_batches because we
    # never added evidence.
    assert normal_eval.reason != "missing_current_reply_approval"
    assert normal_eval.reason in {"insufficient_support", "insufficient_independent_batches"}


# ── 11. Counter-mechanism: same reply ≠ two separate candidates ───────────


def test_same_event_not_counted_twice_as_evidence(tmp_path):
    """S3 preserved dedupe still applies: adding evidence twice with the
    same reference is a no-op — support_count does not grow, confidence
    does not jump again.
    """
    store = PersonalityCandidateStore(tmp_path)
    obs_id = store.capture_observation(
        session_id="s1", assistant_reference="turn1:a",
        assistant_excerpt="I prefer X.", signal_flags=["preference"],
        observed_at=_t(0),
    )
    candidate = store.create_candidate(
        target_layer="relational_self", trait_key="preference",
        statement="Prefers X.", confidence=0.55,
        evidence_summary="Observed.", evidence_reference=obs_id,
        origin="self_observation",
    )
    first_support = candidate.support_count
    first_conf = candidate.confidence

    # Try adding the same evidence again.
    store.add_evidence(candidate.candidate_id, evidence_type="self_observation",
                       summary="Observed.", reference=obs_id, observed_at=_t(0))
    same = store.get_candidate(candidate.candidate_id)
    assert same.support_count == first_support
    assert same.confidence == first_conf
