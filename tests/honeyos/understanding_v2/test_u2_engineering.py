import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.companion.distillation import MemoryDistiller
from honeyos.understanding.u2_context import compose_memory_context
from honeyos.understanding.u2_contracts import (
    BatchEnvelope, ContextSegment, EvidenceUnit, GateAction, Proposal,
    ResolvedModelSpec,
)
from honeyos.understanding.u2_maintenance import apply_proposal
from honeyos.understanding.u2_manage import edit, explain, forget, restore, suppress
from honeyos.understanding.u2_policy import TriggerInput, decide_second_call, extract_signals
from honeyos.understanding.u2_pipeline import process_completed_batch
from honeyos.understanding.u2_proposer import SYSTEM_PROMPT
from honeyos.understanding.u2_runtime import RuntimeMode, expose
from honeyos.understanding.u2_search import lookup_label_ids
from honeyos.understanding.u2_sources import collect_run_evidence
from honeyos.understanding.u2_store import UnderstandingStore, job_id


def _enabled_settings(**overrides):
    values = dict(enabled=True, namespace="general", max_daily_calls=6)
    values.update(overrides)
    return SimpleNamespace(**values)


def evidence(text="我更喜欢先弄懂机制再背结论", ref="e1", group="g1"):
    return EvidenceUnit(ref, "source:1", "r1", group, "user", "message", text,
                        ("learning",), frozenset({"analysis", "chat"}))


def test_signal_and_gate_required_cases():
    signals, fact, chatter = extract_signals((evidence(),))
    assert "preference" in signals and not fact and not chatter
    base = dict(enabled=True, completed=True, after_start=True, sources_allowed=True,
                namespace_allowed=True, suppressed=False, materially_new=True,
                call_issued=False, model_resolved=True, budget_ok=True)
    decision = decide_second_call(TriggerInput(**base, signals=signals), evidence_refs=("e1",))
    assert decision.action == GateAction.RUN and decision.reason == "RUN_PREFERENCE"
    facts, fact_only, _ = extract_signals((evidence("学校是X", "e2", "g2"),))
    assert decide_second_call(TriggerInput(**base, signals=facts, fact_only=fact_only)).reason == "SKIP_FACT_ONLY"
    _, _, chatter_only = extract_signals((evidence("晚安", "e3", "g3"),))
    assert decide_second_call(TriggerInput(**base, signals=frozenset(), chatter_only=chatter_only)).reason == "SKIP_CHATTER"
    assert decide_second_call(TriggerInput(**{**base, "materially_new": False}, signals=signals)).reason == "SKIP_DUPLICATE"


def test_proposal_rejects_program_owned_fields():
    value = {"operation": "propose", "category_id": "interest_preference",
             "scope_key": "learning", "canonical_key": "mechanism_first",
             "text": "可能偏好先理解机制", "support_refs": ["e1"],
             "counter_refs": [], "grade": "high"}
    with pytest.raises(ValueError, match="forbidden"):
        Proposal.from_mapping(value, {"e1"}, {"learning"})


def test_belief_is_not_treated_as_verified_world_fact_or_recycled_inference():
    belief = evidence("我相信某种疗法一定有效", "belief", "belief-event")
    signals, fact_only, chatter = extract_signals((belief,))
    assert not signals and not fact_only and not chatter
    assert "never as proof" in SYSTEM_PROMPT
    with pytest.raises(ValueError, match="derived model text"):
        EvidenceUnit("derived", "label:1", "r1", "g-derived", "user",
                     "model_inference", "你似乎总会拖延", ("work",),
                     frozenset({"analysis", "chat"}))


def test_store_idempotence_maintenance_search_and_forget(tmp_path):
    store = UnderstandingStore(tmp_path / "u2.db")
    store.initialize()
    jid = job_id("o", "l", "n", "run", "hash", "v1")
    args = dict(id=jid, owner="o", lane="l", namespace="n", run_id="run",
                source_hash="hash", pipeline_version="v1", reason="RUN_PREFERENCE")
    assert store.reserve_call(**args)
    assert not store.reserve_call(**args)
    proposal = Proposal("propose", "interest_preference", "learning",
                        "mechanism_first", "似乎偏好先理解机制", ("e1",), ())
    label_id = apply_proposal(store, owner="o", lane="l", namespace="n",
                              proposal=proposal,
                              evidence_meta={"e1": ("g1", "s1", "r1", None)})
    row = explain(store, label_id)["label"]
    assert row["grade"] == "low" and row["state"] == "tentative"
    ids, truncated = lookup_label_ids(store, owner="o", lane="l", namespace="n",
                                      query="理解机制")
    assert label_id in ids and not truncated
    epoch = forget(store, label_id)
    assert epoch == 1
    after = explain(store, label_id)
    assert after["label"]["state"] == "user_suppressed"
    assert after["label"]["body"] == "" and not after["evidence"]


def test_context_budget_and_runtime_modes():
    segments = (
        ContextSegment("a", "src", "1", "memory", "user", "A", 5, 2),
        ContextSegment("dup", "src", "1", "memory", "user", "duplicate", 5, 2),
        ContextSegment("u", "label", "1", "understanding", "inference",
                       "Honey的有限看法：你似乎偏好先理解机制；这可能不准确。", 8, 2),
    )
    result = compose_memory_context(segments, total_budget=20, graph_budget=10,
                                    current_policy_epoch=2)
    assert result.segment_ids == ("a", "u") and result.token_cost == 13
    assert expose(RuntimeMode.OFF, context=result.text, candidate_count=1,
                  estimated_tokens=13).candidate_count == 0
    shadow = expose(RuntimeMode.SHADOW, context=result.text, candidate_count=1,
                    estimated_tokens=13)
    assert not shadow.injected and not shadow.context
    with pytest.raises(PermissionError):
        expose(RuntimeMode.ACTIVE, context=result.text, candidate_count=1,
               estimated_tokens=13)


def test_pipeline_calls_once_and_skips_fact(tmp_path):
    store = UnderstandingStore(tmp_path / "u2.db")
    store.initialize()
    envelope = BatchEnvelope("o", "l", "n", "run", "hash", "rev",
                             datetime.now(timezone.utc))
    calls = 0

    async def call(**kwargs):
        nonlocal calls
        calls += 1
        assert kwargs["retries"] == 0
        return '{"proposals":[]}'

    model = ResolvedModelSpec("provider", "model", "chat_completions")
    first = asyncio.run(process_completed_batch(envelope=envelope, evidence=(evidence(),),
                                                model=model, store=store, call=call,
                                                enabled=True, after_start=True))
    second = asyncio.run(process_completed_batch(envelope=envelope, evidence=(evidence(),),
                                                 model=model, store=store, call=call,
                                                 enabled=True, after_start=True))
    assert first["request_count"] == 1 and first["status"] == "completed"
    assert second["reason"] == "SKIP_COMPLETED"
    assert calls == 1
    fact_envelope = BatchEnvelope("o", "l", "n", "fact", "hash2", "rev2",
                                  datetime.now(timezone.utc))
    fact = asyncio.run(process_completed_batch(envelope=fact_envelope,
        evidence=(evidence("学校是X", "e2", "g2"),), model=model, store=store,
        call=call, enabled=True, after_start=True))
    assert fact["reason"] == "SKIP_FACT_ONLY" and calls == 1


def test_disabled_gate_never_calls_model(tmp_path):
    store = UnderstandingStore(tmp_path / "u2.db")
    store.initialize()
    envelope = BatchEnvelope("o", "l", "n", "disabled", "hash", "rev",
                             datetime.now(timezone.utc))
    calls = 0

    async def call(**kwargs):
        nonlocal calls
        calls += 1
        return '{"proposals":[]}'

    model = ResolvedModelSpec("provider", "model", "chat_completions")
    result = asyncio.run(process_completed_batch(
        envelope=envelope, evidence=(evidence(),), model=model, store=store,
        call=call, enabled=False, after_start=True,
    ))
    assert result["action"] == GateAction.SKIP
    assert result["reason"] == "SKIP_DISABLED"
    assert result["request_count"] == 0 and calls == 0


def test_response_saved_recovers_without_network_resend(tmp_path):
    store = UnderstandingStore(tmp_path / "u2.db")
    store.initialize()
    envelope = BatchEnvelope("o", "l", "n", "recover", "hash-r", "rev-r",
                             datetime.now(timezone.utc))
    jid = job_id("o", "l", "n", "recover", "hash-r", envelope.pipeline_version)
    assert store.reserve_call(id=jid, owner="o", lane="l", namespace="n", run_id="recover",
                              source_hash="hash-r", pipeline_version=envelope.pipeline_version,
                              reason="RUN_PREFERENCE")
    store.save_response(jid, '{"proposals":[{"operation":"propose",'
                        '"category_id":"interest_preference","scope_key":"learning",'
                        '"canonical_key":"mechanism_first","text":"可能偏好先理解机制",'
                        '"support_refs":["e1"],"counter_refs":[]}]}')
    calls = 0
    async def forbidden_call(**kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("recovery must not call model")
    result = asyncio.run(process_completed_batch(
        envelope=envelope, evidence=(evidence(),),
        model=ResolvedModelSpec("p", "m"), store=store, call=forbidden_call,
        enabled=True, after_start=True))
    assert result["status"] == "completed" and result["request_count"] == 0
    assert calls == 0
    assert store.list_labels("o", "l", "n")[0]["grade"] == "low"


def test_gateway_worker_restart_recovers_once_and_blocks_withdrawn_source(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    store.initialize()

    def saved(run_id, source_hash, ref):
        jid = job_id("o", "l", "n", run_id, source_hash, "u2-v1")
        assert store.reserve_call(id=jid, owner="o", lane="l", namespace="n",
                                  run_id=run_id, source_hash=source_hash,
                                  pipeline_version="u2-v1", reason="RUN_PREFERENCE")
        store.save_response(jid, '{"proposals":[{"operation":"propose",'
                            '"category_id":"interest_preference","scope_key":"learning",'
                            f'"canonical_key":"{run_id}","text":"有限理解",'
                            f'"support_refs":["{ref}"],"counter_refs":[]}}]}}')
        return jid

    allowed_id = saved("allowed", "hash-a", "e1")
    blocked_id = saved("blocked", "hash-b", "withdrawn")
    allowed = evidence(ref="e1", group="g1")
    withdrawn = EvidenceUnit("withdrawn", "source:2", "r1", "g2", "user", "message",
                             "我更喜欢先理解", ("learning",), frozenset({"chat"}))

    runner = object.__new__(GatewayRunner)
    runner._u2_recovery_resolver = lambda row: (
        (allowed,) if row["id"] == allowed_id else (withdrawn,)
    )
    first = runner._recover_honeyos_u2_pending(settings=_enabled_settings())
    with store.connect() as db:
        applied_revision = db.execute("SELECT revision FROM labels WHERE canonical_key='allowed'").fetchone()[0]
        # Simulate a process crash after deterministic maintenance but before
        # the completed receipt became durable.
        db.execute("UPDATE jobs SET status='response_saved' WHERE id=?", (allowed_id,))
    second = runner._recover_honeyos_u2_pending(settings=_enabled_settings())
    assert first == {"completed": 1, "blocked": 1, "failed": 0, "model_calls": 0}
    assert second == {"completed": 1, "blocked": 1, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (allowed_id,)).fetchone()[0] == "completed"
        assert db.execute("SELECT status FROM jobs WHERE id=?", (blocked_id,)).fetchone()[0] == "response_saved"
        assert db.execute("SELECT COUNT(*) FROM evidence WHERE evidence_ref='e1'").fetchone()[0] == 1
        assert db.execute("SELECT revision FROM labels WHERE canonical_key='allowed'").fetchone()[0] == applied_revision
    assert len(store.list_labels("o", "l", "n")) == 1


def _continuity_db(path, *, status="active", updated_at=None):
    stamp = updated_at or datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE structured_memories (
                id TEXT PRIMARY KEY,lane_key TEXT,kind TEXT,status TEXT,
                source_session_id TEXT,source_message_ids TEXT,
                created_at TEXT,updated_at TEXT,expires_at TEXT,content TEXT
            );
        """)
        db.execute("INSERT INTO structured_memories VALUES(?,?,?,?,?,?,?,?,?,?)",
                   ("episode", "l", "episode", status, "s1", "[1]", stamp, stamp,
                    None, "PRIVATE BODY"))
    return stamp


def _saved_recovery_job(store, revision, *, run_id="run", source_hash="hash", ref="e1"):
    envelope = BatchEnvelope("o", "l", "n", run_id, source_hash, "rev",
                             datetime.now(timezone.utc))
    jid = job_id("o", "l", "n", run_id, source_hash, envelope.pipeline_version)
    assert store.reserve_call(id=jid, owner="o", lane="l", namespace="n",
                              run_id=run_id, source_hash=source_hash,
                              pipeline_version=envelope.pipeline_version,
                              reason="RUN_PREFERENCE")
    store.save_response(jid, '{"proposals":[{"operation":"propose",'
                        '"category_id":"interest_preference","scope_key":"learning",'
                        f'"canonical_key":"{run_id}","text":"有限理解",'
                        f'"support_refs":["{ref}"],"counter_refs":[]}}]}}')
    store.save_job_evidence(jid, (EvidenceUnit(
        ref, "honeyos_structured:episode", revision, "g1", "user", "message",
        "原文", ("learning",), frozenset({"analysis"})),))
    return jid


def test_gateway_worker_uses_formal_resolver_and_rechecks_live_source(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    revision = _continuity_db(tmp_path / "continuity.db")
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    store.initialize()
    jid = _saved_recovery_job(store, revision)

    # No injected test resolver: the production entry must bind the existing
    # ContinuitySourceResolver and re-read the live source before committing.
    runner = object.__new__(GatewayRunner)
    assert not hasattr(runner, "_u2_recovery_resolver")
    # Disabled (the config default here) leaves the durable job untouched.
    assert runner._recover_honeyos_u2_pending() == {
        "completed": 0, "blocked": 0, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "response_saved"
        assert db.execute("SELECT COUNT(*) FROM labels").fetchone()[0] == 0
    first = runner._recover_honeyos_u2_pending(settings=_enabled_settings())
    assert first == {"completed": 1, "blocked": 0, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        applied_revision = db.execute(
            "SELECT revision FROM labels WHERE canonical_key='run'").fetchone()[0]
        # Crash after maintenance but before the completed receipt.
        db.execute("UPDATE jobs SET status='response_saved' WHERE id=?", (jid,))

    second = runner._recover_honeyos_u2_pending(settings=_enabled_settings())
    assert second == {"completed": 1, "blocked": 0, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "completed"
        assert db.execute("SELECT revision FROM labels WHERE canonical_key='run'").fetchone()[0] == applied_revision
        assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1

    # Withdrawn source: the same saved response must not be applied again.
    with sqlite3.connect(tmp_path / "continuity.db") as db:
        db.execute("UPDATE structured_memories SET status='forgotten' WHERE id='episode'")
    with store.connect() as db:
        db.execute("UPDATE jobs SET status='response_saved' WHERE id=?", (jid,))
    blocked = runner._recover_honeyos_u2_pending(settings=_enabled_settings())
    assert blocked == {"completed": 0, "blocked": 1, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "response_saved"
        assert db.execute("SELECT revision FROM labels WHERE canonical_key='run'").fetchone()[0] == applied_revision

    # Same row restored but its revision moved: stale evidence stays blocked.
    _continuity_db_revision = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(tmp_path / "continuity.db") as db:
        db.execute("UPDATE structured_memories SET status='active',updated_at=? WHERE id='episode'",
                   (_continuity_db_revision,))
    assert runner._recover_honeyos_u2_pending(settings=_enabled_settings()) == {
        "completed": 0, "blocked": 1, "failed": 0, "model_calls": 0}


def test_disabled_recovery_preserves_existing_job_and_resumes_when_reenabled(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    store.initialize()
    jid = _saved_recovery_job(store, "r1")
    db_path = tmp_path / "understanding_v2.db"
    before = db_path.read_bytes()

    runner = object.__new__(GatewayRunner)
    runner._u2_recovery_resolver = lambda row: (EvidenceUnit(
        "e1", "honeyos_structured:episode", "r1", "g1", "user", "message",
        "原文", ("learning",), frozenset({"analysis"})),)
    zeros = {"completed": 0, "blocked": 0, "failed": 0, "model_calls": 0}

    assert runner._recover_honeyos_u2_pending(
        settings=SimpleNamespace(enabled=False, namespace="general", max_daily_calls=6)) == zeros
    # No config file means the loader default also stays disabled.
    assert runner._recover_honeyos_u2_pending() == zeros
    assert db_path.read_bytes() == before
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "response_saved"
        assert db.execute("SELECT COUNT(*) FROM labels").fetchone()[0] == 0

    assert runner._recover_honeyos_u2_pending(settings=_enabled_settings()) == {
        "completed": 1, "blocked": 0, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "completed"
        revision = db.execute("SELECT revision FROM labels WHERE canonical_key='run'").fetchone()[0]

    # A second enabled pass is idempotent; switching back off changes nothing.
    assert runner._recover_honeyos_u2_pending(settings=_enabled_settings()) == zeros
    assert runner._recover_honeyos_u2_pending(
        settings=SimpleNamespace(enabled=False, namespace="general", max_daily_calls=6)) == zeros
    with store.connect() as db:
        assert db.execute("SELECT revision FROM labels WHERE canonical_key='run'").fetchone()[0] == revision


def test_disabled_understanding_startup_recovery_never_creates_or_touches_store(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    runner = object.__new__(GatewayRunner)

    assert not (tmp_path / "understanding_v2.db").exists()
    assert runner._recover_honeyos_u2_pending() == {
        "completed": 0, "blocked": 0, "failed": 0, "model_calls": 0}
    # U2 stays fully dormant while disabled: no database, no derived files.
    assert list(tmp_path.iterdir()) == []


def test_disabled_understanding_gateway_hook_returns_before_any_write(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    runner = object.__new__(GatewayRunner)
    settings = SimpleNamespace(enabled=False, namespace="general", max_daily_calls=6)

    asyncio.run(runner._honeyos_u2_post_completed(
        job=None, result=None, main_runtime={}, settings=settings))
    assert list(tmp_path.iterdir()) == []


def _write_live_config(home, *, enabled: bool = True, namespace: str = "general"):
    flag = "true" if enabled else "false"
    (home / "config.yaml").write_text(
        "memory:\n"
        "  distillation:\n"
        "    enabled: true\n"
        "    trigger_messages: 1\n"
        "    min_tail_messages: 1\n"
        "    max_batch_messages: 10\n"
        "    max_operations: 2\n"
        "    max_attempts: 3\n"
        "    max_daily_runs: 12\n"
        "    understanding:\n"
        f"      enabled: {flag}\n"
        f"      namespace: {namespace}\n"
        "      max_daily_calls: 5\n",
        encoding="utf-8",
    )


def _fake_extractor(calls):
    async def extractor(job, active_items, main_runtime):
        calls.append(job.run_id)
        user = next(message for message in job.messages if message["role"] == "user")
        return json.dumps({
            "chapter": {"title": "聊到先理解机制", "summary": "我们聊过这件事。",
                        "evidence_message_ids": [user["_row_id"]]},
            "operations": [{
                "action": "record",
                "kind": "episode",
                "content": "我记得我们聊过先理解机制",
                "evidence_message_ids": [user["_row_id"]],
            }],
        }, ensure_ascii=False)

    return extractor


def _fake_proposal_call(calls):
    async def call(task=None, **kwargs):
        calls.append(task)
        payload = json.loads(kwargs["messages"][1]["content"])
        item = payload["evidence"][0]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps({"proposals": [{
                "operation": "propose",
                "category_id": "learning_work_style",
                "scope_key": item["scope_keys"][0],
                "canonical_key": "mechanism_first",
                "text": "似乎偏好先理解机制",
                "support_refs": [item["ref"]],
                "counter_refs": [],
            }]}, ensure_ascii=False)))]) 

    return call


async def _drain(runner):
    tasks = list(getattr(runner, "_background_tasks", ()))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _schedule_and_drain(runner, **kwargs):
    # Integration baseline's distillation reloads the transcript tail before
    # preparing a job. The real GatewayRunner owns an AsyncSessionStore; this
    # isolated test runner does not, so provide the same messages it was given.
    if not hasattr(runner, "async_session_store"):
        class _StubAsyncSessionStore:
            def __init__(self, store):
                self._store = store

            async def load_transcript(self, session_id, include_row_ids=True):
                return list(kwargs.get("messages") or [])

        store = object()
        runner.session_store = store
        runner._async_session_store = _StubAsyncSessionStore(store)
    scheduled = runner._schedule_honeyos_memory_distillation(**kwargs)
    await _drain(runner)
    return scheduled


def test_gateway_live_producer_runs_once_and_respects_signal_gate(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner

    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    _write_live_config(tmp_path)
    extractor_calls, u2_calls = [], []
    monkeypatch.setattr(
        "honeyos.companion.distillation.active_honeyos_distiller",
        lambda: MemoryDistiller(tmp_path, extractor=_fake_extractor(extractor_calls)),
    )
    monkeypatch.setattr("honeyos.agent.auxiliary_client.async_call_llm",
                        _fake_proposal_call(u2_calls))

    runner = object.__new__(GatewayRunner)
    assert asyncio.run(_schedule_and_drain(
        runner,
        lane_key="lane", chat_type="dm", session_id="s1",
        messages=[
            {"_row_id": 1, "role": "user", "content": "我更喜欢先弄懂机制再背结论"},
            {"_row_id": 2, "role": "assistant", "content": "明白，我们慢一点来。"},
        ],
        reason="new",
        main_runtime={"provider": "prov", "model": "mdl", "api_mode": "chat_completions"},
    )) is True

    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    assert len(extractor_calls) == 1 and len(u2_calls) == 1
    labels = store.list_labels("local-owner", "lane", "general")
    assert len(labels) == 1 and labels[0]["grade"] == "low"
    with store.connect() as db:
        jobs = db.execute("SELECT status FROM jobs").fetchall()
    assert [row[0] for row in jobs] == ["completed"]

    # Same completed source cannot produce a second review or proposal call.
    asyncio.run(_schedule_and_drain(
        runner,
        lane_key="lane", chat_type="dm", session_id="s1",
        messages=[
            {"_row_id": 1, "role": "user", "content": "我更喜欢先弄懂机制再背结论"},
            {"_row_id": 2, "role": "assistant", "content": "明白，我们慢一点来。"},
        ],
        reason="new",
        main_runtime={"provider": "prov", "model": "mdl"},
    ))
    assert len(extractor_calls) == 1 and len(u2_calls) == 1
    assert len(store.list_labels("local-owner", "lane", "general")) == 1
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1

    # A factual batch is distilled but the live U2 gate never calls the model.
    asyncio.run(_schedule_and_drain(
        runner,
        lane_key="lane", chat_type="dm", session_id="s2",
        messages=[
            {"_row_id": 1, "role": "user", "content": "学校是X"},
            {"_row_id": 2, "role": "assistant", "content": "我记住了。"},
        ],
        reason="new",
        main_runtime={"provider": "prov", "model": "mdl"},
    ))
    assert len(extractor_calls) == 2 and len(u2_calls) == 1
    assert len(store.list_labels("local-owner", "lane", "general")) == 1


def test_gateway_live_producer_failure_never_changes_distillation(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner

    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    _write_live_config(tmp_path)
    extractor_calls = []
    monkeypatch.setattr(
        "honeyos.companion.distillation.active_honeyos_distiller",
        lambda: MemoryDistiller(tmp_path, extractor=_fake_extractor(extractor_calls)),
    )

    async def failing_call(task=None, **kwargs):
        raise RuntimeError("proposal transport failed")

    monkeypatch.setattr("honeyos.agent.auxiliary_client.async_call_llm", failing_call)
    runner = object.__new__(GatewayRunner)
    assert asyncio.run(_schedule_and_drain(
        runner,
        lane_key="lane", chat_type="dm", session_id="s3",
        messages=[
            {"_row_id": 1, "role": "user", "content": "我更喜欢先弄懂机制再背结论"},
            {"_row_id": 2, "role": "assistant", "content": "明白。"},
        ],
        reason="new",
        main_runtime={"provider": "prov", "model": "mdl"},
    )) is True

    with sqlite3.connect(tmp_path / "continuity.db") as db:
        status = db.execute("SELECT status FROM distillation_runs").fetchone()[0]
    assert status == "completed"
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    assert store.list_labels("local-owner", "lane", "general") == []
    with store.connect() as db:
        rows = db.execute("SELECT status FROM jobs").fetchall()
    assert [row[0] for row in rows] == ["call_started"]


def test_live_evidence_reads_authorized_original_text_and_drops_revoked(tmp_path):
    memories = StructuredMemoryStore(tmp_path)
    item = memories.record(
        lane_key="lane", kind="episode", content="伴侣摘要正文",
        evidence="user_stated", source_session_id="s1",
        source_message_ids=(1,), distillation_run_id="run-x",
        created_by="background",
    )
    assert item is not None
    units = collect_run_evidence(
        db_path=tmp_path / "continuity.db", owner="local-owner", lane="lane",
        namespace="general", run_id="run-x", session_id="s1",
        user_messages={1: "我更喜欢先弄懂机制再背结论"},
        scope_keys=("general",),
    )
    assert len(units) == 1
    assert units[0].text == "我更喜欢先弄懂机制再背结论"
    assert units[0].ref == f"honeyos_structured:{item.id}"
    assert units[0].original_message_refs == ("s1:1",)

    # A different live session cannot borrow this source.
    assert collect_run_evidence(
        db_path=tmp_path / "continuity.db", owner="local-owner", lane="lane",
        namespace="general", run_id="run-x", session_id="s2",
        user_messages={1: "我更喜欢先弄懂机制再背结论"},
        scope_keys=("general",),
    ) == ()

    with sqlite3.connect(tmp_path / "continuity.db") as db:
        db.execute("UPDATE structured_memories SET status='forgotten' WHERE id=?",
                   (item.id,))
    assert collect_run_evidence(
        db_path=tmp_path / "continuity.db", owner="local-owner", lane="lane",
        namespace="general", run_id="run-x", session_id="s1",
        user_messages={1: "我更喜欢先弄懂机制再背结论"},
        scope_keys=("general",),
    ) == ()


def test_e2e_enabled_gateway_flow_then_management_lifecycle(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner

    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    _write_live_config(tmp_path)
    extractor_calls, u2_calls = [], []
    monkeypatch.setattr(
        "honeyos.companion.distillation.active_honeyos_distiller",
        lambda: MemoryDistiller(tmp_path, extractor=_fake_extractor(extractor_calls)),
    )
    monkeypatch.setattr("honeyos.agent.auxiliary_client.async_call_llm",
                        _fake_proposal_call(u2_calls))
    runner = object.__new__(GatewayRunner)

    asyncio.run(_schedule_and_drain(
        runner, lane_key="lane", chat_type="dm", session_id="s1",
        messages=[
            {"_row_id": 1, "role": "user", "content": "我更喜欢先弄懂机制再背结论"},
            {"_row_id": 2, "role": "assistant", "content": "明白，我们慢一点来。"},
        ],
        reason="new",
        main_runtime={"provider": "prov", "model": "mdl", "api_mode": "chat_completions"},
    ))

    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    items, total = store.page_labels("local-owner", "lane", "general")
    assert total == 1 and len(items) == 1
    label_id = items[0]["id"]
    detail = explain(store, label_id, owner="local-owner", lane="lane", namespace="general")
    assert detail["label"]["grade"] == "low"
    assert len(detail["evidence"]) == 1
    assert detail["evidence"][0]["source_status"] == "recorded_unverified"
    calls_after_producer = len(u2_calls)

    edited = edit(store, label_id, "我更准确的表述",
                  owner="local-owner", lane="lane", namespace="general")
    assert edited >= 1
    row = explain(store, label_id, owner="local-owner", lane="lane", namespace="general")["label"]
    assert row["body"] == "我更准确的表述" and row["state"] == "tentative" and row["grade"] == "low"

    suppress(store, label_id, owner="local-owner", lane="lane", namespace="general")
    row = explain(store, label_id, owner="local-owner", lane="lane", namespace="general")["label"]
    assert row["state"] == "user_suppressed" and row["body"] == ""
    filtered, filtered_total = store.page_labels(
        "local-owner", "lane", "general", state="user_suppressed")
    assert filtered_total == 1 and filtered[0]["id"] == label_id

    restore(store, label_id, owner="local-owner", lane="lane", namespace="general")
    row = explain(store, label_id, owner="local-owner", lane="lane", namespace="general")["label"]
    assert row["state"] == "needs_reassessment" and row["body"] == "我更准确的表述"

    suppress(store, label_id, owner="local-owner", lane="lane", namespace="general")
    forget(store, label_id, owner="local-owner", lane="lane", namespace="general")
    detail = explain(store, label_id, owner="local-owner", lane="lane", namespace="general")
    assert detail["label"]["state"] == "user_suppressed"
    assert detail["label"]["body"] == "" and detail["evidence"] == []
    # Management never triggers another proposal request.
    assert len(u2_calls) == calls_after_producer == 1


def test_e2e_disabled_then_enabled_recovery_is_bounded_and_source_checked(monkeypatch, tmp_path):
    from honeyos.gateway.run import GatewayRunner

    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home", lambda: tmp_path)
    revision = _continuity_db(tmp_path / "continuity.db")
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    store.initialize()
    jid = _saved_recovery_job(store, revision)
    db_path = tmp_path / "understanding_v2.db"
    zeros = {"completed": 0, "blocked": 0, "failed": 0, "model_calls": 0}
    runner = object.__new__(GatewayRunner)

    _write_live_config(tmp_path, enabled=False)
    before = db_path.read_bytes()
    assert runner._recover_honeyos_u2_pending() == zeros
    assert db_path.read_bytes() == before
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "response_saved"
        assert db.execute("SELECT COUNT(*) FROM labels").fetchone()[0] == 0
    files_after_disable = sorted(p.name for p in tmp_path.iterdir())

    _write_live_config(tmp_path, enabled=True)
    assert runner._recover_honeyos_u2_pending() == {
        "completed": 1, "blocked": 0, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "completed"
        applied_revision = db.execute(
            "SELECT revision FROM labels WHERE canonical_key='run'").fetchone()[0]
    # U2 only adds its own database; no G2/physiology/Cognitive side channels.
    assert sorted(p.name for p in tmp_path.iterdir()) == files_after_disable

    # Simulated crash after maintenance: replay is idempotent, no extra evidence.
    with store.connect() as db:
        db.execute("UPDATE jobs SET status='response_saved' WHERE id=?", (jid,))
    assert runner._recover_honeyos_u2_pending() == {
        "completed": 1, "blocked": 0, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        assert db.execute(
            "SELECT revision FROM labels WHERE canonical_key='run'").fetchone()[0] == applied_revision
        assert db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 1

    # Withdrawn live source blocks promotion and leaves the job for review.
    with sqlite3.connect(tmp_path / "continuity.db") as db:
        db.execute("UPDATE structured_memories SET status='forgotten' WHERE id='episode'")
    with store.connect() as db:
        db.execute("UPDATE jobs SET status='response_saved' WHERE id=?", (jid,))
    assert runner._recover_honeyos_u2_pending() == {
        "completed": 0, "blocked": 1, "failed": 0, "model_calls": 0}
    with store.connect() as db:
        assert db.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()[0] == "response_saved"
        assert db.execute(
            "SELECT revision FROM labels WHERE canonical_key='run'").fetchone()[0] == applied_revision

    # Disabling again is inert even with a durable pending job and a live DB.
    _write_live_config(tmp_path, enabled=False)
    continuity_bytes = (tmp_path / "continuity.db").read_bytes()
    pending_bytes = db_path.read_bytes()
    assert runner._recover_honeyos_u2_pending() == zeros
    assert db_path.read_bytes() == pending_bytes
    assert (tmp_path / "continuity.db").read_bytes() == continuity_bytes


def test_e2e_owner_lane_namespace_isolation(tmp_path):
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    store.initialize()
    proposal = Proposal("propose", "interest_preference", "learning",
                        "mechanism_first", "有限理解", ("e1",), ())
    meta = {"e1": ("g1", "s1", "r1", None)}
    id_a = apply_proposal(store, owner="o", lane="l", namespace="n",
                          proposal=proposal, evidence_meta=meta)
    id_b = apply_proposal(store, owner="o2", lane="l2", namespace="n2",
                          proposal=proposal, evidence_meta=meta)

    rows, total = store.page_labels("o", "l", "n")
    assert total == 1 and rows[0]["id"] == id_a
    assert store.page_labels("o", "l", "n2") == ([], 0)
    assert store.page_labels("o2", "l2", "n2")[1] == 1

    with pytest.raises(PermissionError):
        explain(store, id_b, owner="o", lane="l", namespace="n")
    with pytest.raises(PermissionError):
        suppress(store, id_b, owner="o", lane="l", namespace="n")
    with pytest.raises(PermissionError):
        edit(store, id_b, "越权修改", owner="o", lane="l", namespace="n")
    # The foreign label is untouched.
    assert explain(store, id_b, owner="o2", lane="l2", namespace="n2")["label"]["body"] == "有限理解"
