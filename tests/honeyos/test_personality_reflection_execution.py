from __future__ import annotations

import json
from types import SimpleNamespace

from honeyos.companion.personality_candidates import PersonalityCandidateStore
from honeyos.companion.personality_reflection_execution import (
    AuxiliaryPersonalityReflectionAdapter,
    maybe_start_background_personality_reflection,
    run_personality_reflection_once,
)


def _capture(store, count):
    ids = []
    for i in range(count):
        ids.append(
            store.capture_observation(
                session_id="s",
                signal_flags=["preference"],
                assistant_excerpt=f"I prefer option {i}.",
            )
        )
    return ids


def test_below_threshold_causes_zero_model_calls(monkeypatch, tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 4)

    called = False

    def fake_call_llm(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("must not call model")

    monkeypatch.setattr(
        "honeyos.agent.auxiliary_client.call_llm",
        fake_call_llm,
    )

    result = run_personality_reflection_once(tmp_path)

    assert result["status"] == "skipped"
    assert called is False


def test_real_adapter_uses_auxiliary_client_and_creates_candidate(monkeypatch, tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    ids = _capture(store, 20)
    captured = {}

    class Response:
        model = "test-model"
        provider = "test-provider"
        usage = SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
        )
        choices = [
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
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
                    )
                )
            )
        ]

    def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(
        "honeyos.agent.auxiliary_client.call_llm",
        fake_call_llm,
    )

    result = run_personality_reflection_once(
        tmp_path,
        main_runtime={
            "provider": "custom",
            "model": "test-model",
            "base_url": "https://example.invalid/v1",
            "api_mode": "chat_completions",
        },
    )

    assert result["status"] == "success"
    assert captured["task"] == "personality_reflection"
    assert captured["main_runtime"]["api_mode"] == "chat_completions"
    assert store.pending_observation_count() == 0
    candidates = store.list_candidates(status="candidate")
    assert len(candidates) == 1
    assert candidates[0].trait_key == "independent_preference"

    system_prompt = captured["messages"][0]["content"]
    user_payload = json.loads(captured["messages"][1]["content"])
    assert "Prefer no operation over a weak personality conclusion." in system_prompt
    assert "observations" in user_payload
    assert "candidates" not in user_payload


def test_model_usage_is_audited(monkeypatch, tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 20)

    response = SimpleNamespace(
        model="m",
        provider="p",
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
        ),
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content='{"operations":[]}')
            )
        ],
    )

    monkeypatch.setattr(
        "honeyos.agent.auxiliary_client.call_llm",
        lambda **kwargs: response,
    )

    result = run_personality_reflection_once(tmp_path)
    assert result["status"] == "success"

    audit = store.audit_path.read_text(encoding="utf-8")
    assert '"event": "reflection_model_call"' in audit
    assert '"prompt_tokens": 11' in audit
    assert '"completion_tokens": 7' in audit
    assert '"total_tokens": 18' in audit


def test_failed_model_call_keeps_pending(monkeypatch, tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 20)

    def fail(**kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        "honeyos.agent.auxiliary_client.call_llm",
        fail,
    )

    result = run_personality_reflection_once(tmp_path)

    assert result["status"] == "failed"
    assert store.pending_observation_count() == 20
    assert store.list_candidates() == []


def test_runtime_trigger_does_not_start_thread_below_threshold(monkeypatch, tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    _capture(store, 3)

    started = False

    class ForbiddenThread:
        def __init__(self, *args, **kwargs):
            nonlocal started
            started = True
            raise AssertionError("thread must not be created below threshold")

    monkeypatch.setattr(
        "honeyos.companion.personality_reflection_execution.threading.Thread",
        ForbiddenThread,
    )

    result = maybe_start_background_personality_reflection(tmp_path)
    assert result["started"] is False
    assert started is False


def test_adapter_payload_contains_only_bounded_batch_not_candidate_state(monkeypatch, tmp_path):
    store = PersonalityCandidateStore(tmp_path)
    ids = _capture(store, 20)
    store.create_candidate(
        target_layer="relational_self",
        trait_key="existing_trait",
        statement="Existing candidate must not feed back into reflection prompt.",
        confidence=0.8,
    )
    captured = {}

    response = SimpleNamespace(
        usage=None,
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"operations":[]}'))],
    )

    def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return response

    adapter = AuxiliaryPersonalityReflectionAdapter(tmp_path)
    batch = {
        "batch_id": "batch",
        "observations": [
            {
                "observation_id": ids[0],
                "signal_flags": ["preference"],
                "user_excerpt": "",
                "assistant_excerpt": "I prefer this.",
                "observed_at": "",
            }
        ],
    }
    monkeypatch.setattr(
        "honeyos.agent.auxiliary_client.call_llm",
        fake_call_llm,
    )

    assert adapter(batch) == '{"operations":[]}'
    payload = captured["messages"][1]["content"]
    assert "existing_trait" not in payload
    assert "Existing candidate must not feed back" not in payload
