"""Completed-batch U2 orchestration, isolated from the original result."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .u2_contracts import BatchEnvelope, EvidenceUnit, GateAction, ResolvedModelSpec
from .u2_policy import TriggerInput, decide_second_call, extract_signals
from .u2_maintenance import apply_proposal
from .u2_proposer import parse_response, propose_once
from .u2_store import UnderstandingStore, job_id


async def process_completed_batch(*, envelope: BatchEnvelope,
                                  evidence: tuple[EvidenceUnit, ...],
                                  model: ResolvedModelSpec | None,
                                  store: UnderstandingStore,
                                  call: Callable[..., Awaitable[str]],
                                  enabled: bool, after_start: bool,
                                  materially_new: bool = True,
                                  budget_ok: bool = True) -> dict:
    """Run at most one proposal request after original completion.

    Callers must supply already-filtered, revision-checked evidence. A U2
    failure is returned as its own receipt and must not mutate the original
    distillation result.
    """
    signals, fact_only, chatter_only = extract_signals(evidence)
    jid = job_id(envelope.owner_id, envelope.lane, envelope.namespace,
                 envelope.run_id, envelope.source_hash, envelope.pipeline_version)
    with store.connect() as db:
        row = db.execute("SELECT call_issued,status,response_json FROM jobs WHERE id=?", (jid,)).fetchone()
    if row and row["status"] == "response_saved" and row["response_json"]:
        try:
            count = recover_saved_response(envelope=envelope, evidence=evidence, store=store,
                                           response_json=row["response_json"], jid=jid)
        except (PermissionError, RuntimeError, ValueError) as exc:
            return {"job_id": jid, "action": GateAction.BLOCKED,
                    "reason": "BLOCKED_SOURCE_RECHECK", "request_count": 0,
                    "status": "response_saved", "error_type": type(exc).__name__}
        return {"job_id": jid, "action": GateAction.RUN, "reason": "RECOVER_RESPONSE_SAVED",
                "request_count": 0, "proposal_count": count, "status": "completed"}
    if row and row["status"] == "completed":
        return {"job_id": jid, "action": GateAction.SKIP, "reason": "SKIP_COMPLETED",
                "request_count": 0, "status": "completed"}
    decision = decide_second_call(TriggerInput(
        enabled=enabled, completed=True, after_start=after_start,
        sources_allowed=bool(evidence) and all("analysis" in item.purposes for item in evidence),
        namespace_allowed=bool(envelope.namespace), suppressed=False,
        materially_new=materially_new, call_issued=bool(row and row["call_issued"]),
        model_resolved=model is not None, budget_ok=budget_ok, signals=signals,
        fact_only=fact_only, chatter_only=chatter_only,
    ), evidence_refs=tuple(item.ref for item in evidence))
    receipt = {"job_id": jid, "action": decision.action, "reason": decision.reason,
               "request_count": 0}
    if decision.action != GateAction.RUN:
        return receipt
    assert model is not None
    reserved = store.reserve_call(id=jid, owner=envelope.owner_id, lane=envelope.lane,
                                  namespace=envelope.namespace, run_id=envelope.run_id,
                                  source_hash=envelope.source_hash,
                                  pipeline_version=envelope.pipeline_version,
                                  reason=decision.reason)
    if not reserved:
        return {**receipt, "action": GateAction.SKIP, "reason": "SKIP_ALREADY_ISSUED"}
    try:
        # Persist only source identity/revision metadata so restart recovery can
        # revalidate live permissions without copying any body text.
        store.save_job_evidence(jid, evidence)
    except Exception as exc:
        return {**receipt, "status": "failed", "error_type": type(exc).__name__}
    receipt["request_count"] = 1
    try:
        proposals = await propose_once(model=model, evidence=evidence, call=call)
        raw = json.dumps({"proposals": [asdict(p) for p in proposals]}, ensure_ascii=False,
                         default=list)
        store.save_response(jid, raw)
        count = recover_saved_response(envelope=envelope, evidence=evidence, store=store,
                                       response_json=raw, jid=jid)
        return {**receipt, "proposal_count": count, "status": "completed"}
    except Exception as exc:
        # Never resend automatically: call_started remains an explicit uncertain
        # receipt for operator/recovery handling.
        return {**receipt, "status": "uncertain", "error_type": type(exc).__name__}


def resolve_model_from_runtime(main_runtime: Mapping[str, Any] | None) -> ResolvedModelSpec | None:
    """Use only the provider/model the completed turn actually resolved."""
    runtime = dict(main_runtime or {})
    provider = str(runtime.get("provider") or "").strip()
    model = str(runtime.get("model") or "").strip()
    if not provider or not model:
        return None
    return ResolvedModelSpec(provider, model, str(runtime.get("api_mode") or ""))


def build_proposal_call(main_runtime: Mapping[str, Any] | None):
    """Bind one no-retry proposal request to the existing auxiliary client."""
    runtime = {
        key: value
        for key, value in dict(main_runtime or {}).items()
        if key in {"provider", "model", "base_url", "api_key", "api_mode"}
    }

    async def call(*, system: str, user: str, provider: str, model: str,
                   api_mode: str = "", retries: int = 0) -> str:
        if retries:
            raise ValueError("U2 proposals must never resend automatically")
        from honeyos.agent.auxiliary_client import async_call_llm

        response = await async_call_llm(
            task="understanding_u2",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            provider=provider, model=model, main_runtime=dict(runtime),
            # Up to 4 proposals at 360 CJK characters each do not fit in 600
            # tokens; truncation would make the whole response unparseable.
            temperature=0, max_tokens=1400,
        )
        return str(response.choices[0].message.content or "")

    return call


async def produce_after_distillation(*, home: Path, owner: str, lane: str,
                                     namespace: str, run_id: str, source_hash: str,
                                     session_id: str,
                                     user_messages: Mapping[int, str],
                                     model_runtime: Mapping[str, Any] | None,
                                     enabled: bool, max_daily_calls: int,
                                     store: UnderstandingStore,
                                     now: datetime | None = None,
                                     call: Callable[..., Awaitable[str]] | None = None,
                                     ) -> dict | None:
    """Live post-completed producer, additive to the distillation result.

    Evidence comes only from user-stated structured memories written by this
    run, re-authorized through the formal continuity resolver. At most one
    proposal request is issued, and the receipt is advisory: callers must not
    let a U2 failure change the completed distillation result.
    """
    if not enabled:
        return None
    from .u2_sources import collect_run_evidence

    evidence = collect_run_evidence(
        db_path=Path(home) / "continuity.db", owner=owner, lane=lane,
        namespace=namespace, run_id=run_id, session_id=session_id,
        user_messages=user_messages, scope_keys=(namespace,),
    )
    if not evidence:
        return {"action": GateAction.BLOCKED, "reason": "BLOCKED_NO_LIVE_EVIDENCE",
                "request_count": 0}
    timestamp = now or datetime.now(timezone.utc)
    day_start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    budget_ok = store.calls_today(owner=owner, lane=lane, namespace=namespace,
                                  since=day_start) < max(1, int(max_daily_calls))
    envelope = BatchEnvelope(owner, lane, namespace, run_id, source_hash,
                             source_hash, timestamp)
    return await process_completed_batch(
        envelope=envelope, evidence=evidence,
        model=resolve_model_from_runtime(model_runtime), store=store,
        call=call or build_proposal_call(model_runtime), enabled=True,
        after_start=True, budget_ok=budget_ok,
    )


def recover_saved_response(*, envelope: BatchEnvelope, evidence: tuple[EvidenceUnit, ...],
                           store: UnderstandingStore, response_json: str, jid: str,
                           continuity_db_path=None) -> int:
    """Apply a durable response without issuing another model request.

    Evidence rows use stable refs and INSERT OR IGNORE, so repeating recovery
    after a crash cannot increase independent support/counter counts.
    """
    if not evidence or not all("analysis" in item.purposes for item in evidence):
        raise PermissionError("current evidence is not analysis-allowed")
    proposals = parse_response(
        response_json,
        allowed_refs={item.ref for item in evidence},
        allowed_scopes={scope for item in evidence for scope in item.scope_keys},
    )
    evidence_meta = {
        item.ref: (
            item.event_group_id,
            item.original_message_refs[0].split(":", 1)[0] if item.original_message_refs else "",
            item.revision,
            item.occurred_at.isoformat() if item.occurred_at else None,
        ) for item in evidence
    }
    for proposal in proposals:
        apply_proposal(store, owner=envelope.owner_id, lane=envelope.lane,
                       namespace=envelope.namespace, proposal=proposal,
                       evidence_meta=evidence_meta,
                       continuity_db_path=continuity_db_path)
    store.complete(jid)
    return len(proposals)


def recover_pending_jobs(*, store: UnderstandingStore,
                         resolve_evidence: Callable[[dict], tuple[EvidenceUnit, ...] | None],
                         limit: int = 20, continuity_db_path=None) -> dict[str, int]:
    """Bounded worker entry for restart recovery; never performs model calls."""
    with store.connect() as db:
        rows = db.execute("""SELECT * FROM jobs
            WHERE status='response_saved' AND response_json IS NOT NULL
            ORDER BY updated_at,id LIMIT ?""", (max(1, min(limit, 100)),)).fetchall()
    result = {"completed": 0, "blocked": 0, "failed": 0, "model_calls": 0}
    for raw_row in rows:
        row = dict(raw_row)
        try:
            evidence = resolve_evidence(row)
            if not evidence:
                result["blocked"] += 1
                continue
            envelope = BatchEnvelope(
                row["owner"], row["lane"], row["namespace"], row["run_id"],
                row["source_hash"], row["source_hash"], datetime.now(timezone.utc),
                row["pipeline_version"],
            )
            recover_saved_response(envelope=envelope, evidence=evidence, store=store,
                                   response_json=row["response_json"], jid=row["id"],
                                   continuity_db_path=continuity_db_path)
            result["completed"] += 1
        except (PermissionError, RuntimeError, ValueError, KeyError):
            result["blocked"] += 1
        except Exception:
            result["failed"] += 1
    return result

