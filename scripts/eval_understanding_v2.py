"""Budget-first evaluator. Dry-run stays network-free; model mode needs a cap.

The ``synthetic-model`` mode is restricted to a loopback OpenAI-compatible
endpoint and is only run after explicit user approval for R4-MODEL synthetic
evaluation. It sends synthetic evidence only, never production user data.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RUNNABLE_PREFIX = "RUN_"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


def _plan(raw: bytes, data: dict) -> dict:
    runnable = [c for c in data["cases"] if str(c["expected_gate"]).startswith(RUNNABLE_PREFIX)]
    return {
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "synthetic": data.get("synthetic") is True,
        "model": data.get("model"),
        "planned_requests": len(runnable),
        "worst_input_tokens": sum(c["estimated_input_tokens"] for c in runnable),
        "worst_output_tokens": sum(c["estimated_output_tokens"] for c in runnable),
        "cases": [{"case_id": c["case_id"], "expected_gate": c["expected_gate"]}
                  for c in data["cases"]],
    }


def _post_json(endpoint: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _make_local_call(base_url: str, model: str, timeout: float):
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint += "/v1"
    endpoint += "/chat/completions"

    async def call(*, system: str, user: str, provider: str, model: str,
                   api_mode: str = "", retries: int = 0) -> str:
        if retries:
            raise ValueError("evaluation calls must never retry")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 600,
            "stream": False,
        }
        body = await asyncio.to_thread(_post_json, endpoint, payload, timeout)
        return str(body["choices"][0]["message"].get("content") or "")

    return call


def _evidence(case: dict):
    from honeyos.understanding.u2_contracts import EvidenceUnit

    scope_keys = tuple(case.get("scope_keys") or ("general",))
    units = []
    for item in case.get("evidence", ()):
        units.append(EvidenceUnit(
            ref=str(item["ref"]),
            source_ref=f"synthetic:{case['case_id']}",
            revision="r1",
            event_group_id=f"{case['case_id']}-g1",
            role="user",
            kind="message",
            text=str(item["text"]),
            scope_keys=scope_keys,
            purposes=frozenset({"analysis", "chat"}),
        ))
    return tuple(units)


def _gate(evidence):
    from honeyos.understanding.u2_policy import (
        TriggerInput, decide_second_call, extract_signals,
    )

    signals, fact_only, chatter_only = extract_signals(evidence)
    return decide_second_call(
        TriggerInput(
            enabled=True, completed=True, after_start=True,
            sources_allowed=bool(evidence) and all(
                "analysis" in item.purposes for item in evidence),
            namespace_allowed=True, suppressed=False, materially_new=True,
            call_issued=False, model_resolved=True, budget_ok=True,
            signals=signals, fact_only=fact_only, chatter_only=chatter_only,
        ),
        evidence_refs=tuple(item.ref for item in evidence),
    )


async def _evaluate(data: dict, *, base_url: str, model: str, timeout: float,
                    approved_request_cap: int, dataset_sha256: str) -> dict:
    from honeyos.understanding.u2_contracts import BatchEnvelope, GateAction, ResolvedModelSpec
    from honeyos.understanding.u2_pipeline import process_completed_batch
    from honeyos.understanding.u2_store import UnderstandingStore

    store = UnderstandingStore(
        Path(tempfile.mkdtemp(prefix="u2-eval-")) / "understanding_v2.db")
    store.initialize()
    spec = ResolvedModelSpec("local-openai", model, "chat_completions")
    base_call = _make_local_call(base_url, model, timeout)
    captured: dict[str, str] = {}

    async def call(*, system: str, user: str, provider: str, model: str,
                   api_mode: str = "", retries: int = 0) -> str:
        text = await base_call(
            system=system, user=user, provider=provider, model=model,
            api_mode=api_mode, retries=retries,
        )
        captured["last"] = text
        return text

    budget = {"issued": 0, "remaining": max(1, int(approved_request_cap))}
    rows = []

    for case in data["cases"]:
        evidence = _evidence(case)
        if not evidence:
            raise SystemExit(f"case {case['case_id']} has no synthetic evidence")
        decision = _gate(evidence)
        row = {
            "case_id": case["case_id"],
            "expected_gate": case["expected_gate"],
            "actual_gate": decision.reason,
            "action": decision.action.value,
            "gate_match": decision.reason == case["expected_gate"],
            "requests": 0,
            "status": "skipped",
        }
        if decision.action == GateAction.RUN:
            if budget["remaining"] <= 0:
                raise SystemExit("approved request cap exhausted before the run set finished")
            budget["remaining"] -= 1
            budget["issued"] += 1
            envelope = BatchEnvelope(
                "eval-owner", f"eval-{case['case_id']}", "general",
                case["case_id"], dataset_sha256, "r1",
                datetime.now(timezone.utc),
            )
            started = time.perf_counter()
            receipt = await process_completed_batch(
                envelope=envelope, evidence=evidence, model=spec, store=store,
                call=call, enabled=True, after_start=True,
            )
            row.update({
                "requests": int(receipt.get("request_count", 0)),
                "status": receipt.get("status", ""),
                "proposal_count": int(receipt.get("proposal_count", 0)),
                "label_count": len(store.list_labels(
                    "eval-owner", f"eval-{case['case_id']}", "general")),
                "error_type": receipt.get("error_type", ""),
                "latency_s": round(time.perf_counter() - started, 2),
                "raw_preview": captured.get("last", "")[:400],
            })
        rows.append(row)

    run_rows = [row for row in rows if row["action"] == GateAction.RUN.value]
    return {
        "dataset_sha256": dataset_sha256,
        "synthetic": data.get("synthetic") is True,
        "mode": "synthetic-model",
        "model": model,
        "approved_request_cap": approved_request_cap,
        "requests_issued": budget["issued"],
        "gate_cases": len(rows),
        "gate_correct": sum(1 for row in rows if row["gate_match"]),
        "run_cases": len(run_rows),
        "pipeline_completed": sum(1 for row in run_rows if row["status"] == "completed"),
        "proposals_total": sum(int(row.get("proposal_count", 0)) for row in run_rows),
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--mode", choices=("dry-run", "synthetic-model"), required=True)
    parser.add_argument("--approved-request-cap", type=int, default=0)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    raw = args.dataset.read_bytes()
    data = json.loads(raw)
    plan = _plan(raw, data)
    print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
    if args.mode == "dry-run":
        return 0
    if args.approved_request_cap <= 0:
        raise SystemExit("synthetic-model requires an explicit positive approved request cap")
    if not args.base_url or not args.model:
        raise SystemExit("synthetic-model requires --base-url and --model")
    host = (urlparse(args.base_url).hostname or "").lower()
    if host not in LOOPBACK_HOSTS:
        raise SystemExit("synthetic-model is restricted to a loopback base URL")
    report = asyncio.run(_evaluate(
        data, base_url=args.base_url, model=args.model, timeout=args.timeout,
        approved_request_cap=args.approved_request_cap,
        dataset_sha256=plan["dataset_sha256"],
    ))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    ok = report["gate_correct"] == report["gate_cases"]
    return 0 if ok and report["requests_issued"] <= args.approved_request_cap else 1


if __name__ == "__main__":
    raise SystemExit(main())
