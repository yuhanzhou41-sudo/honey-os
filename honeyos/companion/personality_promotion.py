
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from functools import wraps
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from honeyos.companion.personality_candidates import PersonalityCandidateStore

AUTHORITY_VERSION = 1
RELATIONAL_MIN_SUPPORT = 3
RELATIONAL_MIN_CONFIDENCE = 0.65
RELATIONAL_MIN_BATCHES = 2
RELATIONAL_MIN_NON_FEEDBACK_EVIDENCE = 2

STABLE_MIN_SUPPORT = 6
STABLE_MIN_CONFIDENCE = 0.75
STABLE_MIN_BATCHES = 3
STABLE_MIN_SESSIONS = 3
STABLE_MIN_SPAN_DAYS = 7.0
STABLE_MIN_NON_FEEDBACK_EVIDENCE = 4
STABLE_MAX_CONTRADICTIONS = 1
STABLE_MAX_CONTRADICTION_RATIO = 0.25

_ALLOWED_LAYERS = {"relational_self", "stable_core"}
_AUTHORITY_WRITE_LOCK = threading.RLock()
_AUTHORITY_PROMPT_LIMIT = 1200
_RESERVED_TRAIT_KEYS = {
    "name", "companion_name", "assistant_name", "display_name",
    "user_nickname", "relationship", "boundaries", "tool_permissions",
    "safety_policy", "credentials", "account_identity",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(home: Path | str) -> Path:
    return Path(home).expanduser() / "companion"


def _authority_path(home: Path | str) -> Path:
    return _root(home) / "personality_authority.json"


def _audit_path(home: Path | str) -> Path:
    return _root(home) / "personality_promotion_audit.jsonl"


def _empty_authority() -> dict[str, Any]:
    return {
        "version": AUTHORITY_VERSION,
        "relational_self": {},
        "stable_core": {},
        "blocked_candidate_ids": [],
        "user_deleted_traits": [],
        "history": [],
    }


def load_personality_authority(home: Path | str) -> dict[str, Any]:
    path = _authority_path(home)
    if not path.exists():
        return _empty_authority()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_authority()
    if not isinstance(data, dict):
        return _empty_authority()
    base = _empty_authority()
    base.update(data)
    for layer in _ALLOWED_LAYERS:
        if not isinstance(base.get(layer), dict):
            base[layer] = {}
    if not isinstance(base.get("blocked_candidate_ids"), list):
        base["blocked_candidate_ids"] = []
    if not isinstance(base.get("history"), list):
        base["history"] = []
    if not isinstance(base.get("user_deleted_traits"), list):
        base["user_deleted_traits"] = []
    return base


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass


def _audit(home: Path | str, event: str, payload: Mapping[str, Any]) -> None:
    path = _audit_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"event": event, "at": _now_iso(), **dict(payload)}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _candidate_value(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
    except Exception:
        return set()


def _evidence_metrics(store: PersonalityCandidateStore, candidate_id: str) -> dict[str, Any]:
    result = {
        "evidence_count": 0,
        "distinct_batches": 0,
        "distinct_sessions": 0,
        "span_days": 0.0,
        "user_feedback_count": 0,
        "non_feedback_count": 0,
    }
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    try:
        ev_cols = _table_columns(conn, "personality_candidate_evidence")
        obs_cols = _table_columns(conn, "personality_pending_observations")
        if not ev_cols:
            return result
        rows = conn.execute(
            "SELECT * FROM personality_candidate_evidence WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchall()

        ref_col = next(
            (c for c in ("reference", "evidence_reference", "source_reference") if c in ev_cols),
            None,
        )
        type_col = next(
            (c for c in ("evidence_type", "type", "origin") if c in ev_cols),
            None,
        )
        refs: list[str] = []
        ref_types: list[tuple[str, str]] = []
        for row in rows:
            evidence_type = str(row[type_col] or "") if type_col else ""
            if ref_col:
                value = str(row[ref_col] or "").strip()
                if value:
                    refs.append(value)
                    ref_types.append((value, evidence_type))
                    continue
            # Evidence without a source reference cannot be tied to an event,
            # so it counts once on its own.
            result["evidence_count"] += 1
            if evidence_type == "user_feedback":
                result["user_feedback_count"] += 1
            else:
                result["non_feedback_count"] += 1

        if not refs or not obs_cols or "observation_id" not in obs_cols:
            return result

        placeholders = ",".join("?" for _ in refs)
        obs_rows = conn.execute(
            f"SELECT * FROM personality_pending_observations "
            f"WHERE observation_id IN ({placeholders})",
            refs,
        ).fetchall()
        if store.liked_only:
            from honeyos.companion.personality_observation_hook import liked_observation_ids

            result["all_evidence_liked"] = len(refs) == len(rows) and set(refs) == liked_observation_ids(store.home, obs_rows)

        obs_by_id = {str(row["observation_id"]): row for row in obs_rows}
        seen_events: set[str] = set()
        batches: set[str] = set()
        sessions: set[str] = set()
        times: list[datetime] = []
        for reference, evidence_type in ref_types:
            obs_row = obs_by_id.get(reference)
            # One user event can surface as several reply rows (retries, model
            # switches). Count the source event once, never its re-wordings.
            event_key = ""
            if obs_row is not None and "user_reference" in obs_cols:
                event_key = str(obs_row["user_reference"] or "").strip()
            event_key = event_key or reference
            if event_key in seen_events:
                continue
            seen_events.add(event_key)
            result["evidence_count"] += 1
            if evidence_type == "user_feedback":
                result["user_feedback_count"] += 1
            else:
                result["non_feedback_count"] += 1
            if obs_row is None:
                continue
            if "reflection_batch_id" in obs_cols:
                value = str(obs_row["reflection_batch_id"] or "").strip()
                if value:
                    batches.add(value)
            if "session_id" in obs_cols:
                value = str(obs_row["session_id"] or "").strip()
                if value:
                    sessions.add(value)
            if "observed_at" in obs_cols:
                value = str(obs_row["observed_at"] or "").strip()
                if value:
                    try:
                        times.append(datetime.fromisoformat(value))
                    except Exception:
                        pass

        result["distinct_batches"] = len(batches)
        result["distinct_sessions"] = len(sessions)
        if len(times) >= 2:
            result["span_days"] = max(
                0.0, (max(times) - min(times)).total_seconds() / 86400.0
            )
        return result
    finally:
        conn.close()


@dataclass(frozen=True)
class PromotionDecision:
    eligible: bool
    target_layer: str
    reason: str
    metrics: dict[str, Any]


def evaluate_candidate_for_promotion(home: Path | str, candidate: Any, *, liked_only: bool = False) -> PromotionDecision:
    store = PersonalityCandidateStore(home, liked_only=liked_only)
    candidate_id = str(_candidate_value(candidate, "candidate_id", "") or "")
    layer = str(_candidate_value(candidate, "target_layer", "") or "")
    trait_key = str(_candidate_value(candidate, "trait_key", "") or "")
    status = str(_candidate_value(candidate, "status", "candidate") or "candidate")
    support = int(_candidate_value(candidate, "support_count", 0) or 0)
    contradictions = int(_candidate_value(candidate, "contradiction_count", 0) or 0)
    confidence = float(_candidate_value(candidate, "confidence", 0.0) or 0.0)
    metrics = _evidence_metrics(store, candidate_id)
    if liked_only and not metrics.get("all_evidence_liked"):
        return PromotionDecision(False, layer, "missing_current_reply_approval", metrics)
    metrics.update({
        "support_count": support,
        "contradiction_count": contradictions,
        "confidence": confidence,
    })

    authority = load_personality_authority(home)
    if candidate_id in set(authority.get("blocked_candidate_ids") or []):
        return PromotionDecision(False, layer, "blocked_candidate", metrics)
    if status != "candidate":
        return PromotionDecision(False, layer, "not_active_candidate", metrics)
    if layer not in _ALLOWED_LAYERS:
        return PromotionDecision(False, layer, "unsupported_layer", metrics)
    if not trait_key or trait_key in _RESERVED_TRAIT_KEYS:
        return PromotionDecision(False, layer, "reserved_trait", metrics)

    if layer == "relational_self":
        if support < RELATIONAL_MIN_SUPPORT:
            return PromotionDecision(False, layer, "insufficient_support", metrics)
        if confidence < RELATIONAL_MIN_CONFIDENCE:
            return PromotionDecision(False, layer, "insufficient_confidence", metrics)
        if contradictions >= support:
            return PromotionDecision(False, layer, "contradiction_dominates", metrics)
        if metrics["distinct_batches"] < RELATIONAL_MIN_BATCHES:
            return PromotionDecision(False, layer, "insufficient_independent_batches", metrics)
        if metrics["non_feedback_count"] < RELATIONAL_MIN_NON_FEEDBACK_EVIDENCE:
            return PromotionDecision(False, layer, "user_feedback_not_sufficient", metrics)
        return PromotionDecision(True, layer, "mature_relational_candidate", metrics)

    if trait_key not in (authority.get("relational_self") or {}):
        return PromotionDecision(False, layer, "requires_relational_authority", metrics)
    if support < STABLE_MIN_SUPPORT:
        return PromotionDecision(False, layer, "insufficient_support", metrics)
    if confidence < STABLE_MIN_CONFIDENCE:
        return PromotionDecision(False, layer, "insufficient_confidence", metrics)
    if metrics["distinct_batches"] < STABLE_MIN_BATCHES:
        return PromotionDecision(False, layer, "insufficient_independent_batches", metrics)
    if metrics["distinct_sessions"] < STABLE_MIN_SESSIONS:
        return PromotionDecision(False, layer, "insufficient_session_span", metrics)
    if metrics["span_days"] < STABLE_MIN_SPAN_DAYS:
        return PromotionDecision(False, layer, "insufficient_time_span", metrics)
    if metrics["non_feedback_count"] < STABLE_MIN_NON_FEEDBACK_EVIDENCE:
        return PromotionDecision(False, layer, "user_feedback_not_sufficient", metrics)
    ratio = contradictions / max(1, support)
    if contradictions > STABLE_MAX_CONTRADICTIONS or ratio > STABLE_MAX_CONTRADICTION_RATIO:
        return PromotionDecision(False, layer, "too_many_contradictions", metrics)
    return PromotionDecision(True, layer, "mature_stable_candidate", metrics)


def _record(candidate: Any, decision: PromotionDecision) -> dict[str, Any]:
    return {
        "candidate_id": str(_candidate_value(candidate, "candidate_id", "") or ""),
        "trait_key": str(_candidate_value(candidate, "trait_key", "") or ""),
        "statement": str(_candidate_value(candidate, "statement", "") or "").strip(),
        "confidence": float(_candidate_value(candidate, "confidence", 0.0) or 0.0),
        "support_count": int(_candidate_value(candidate, "support_count", 0) or 0),
        "contradiction_count": int(_candidate_value(candidate, "contradiction_count", 0) or 0),
        "promoted_at": _now_iso(),
        "promotion_reason": decision.reason,
        "metrics": dict(decision.metrics),
    }


def _serialized_write(fn):
    @wraps(fn)
    def update(*args, **kwargs):
        with _AUTHORITY_WRITE_LOCK:
            return fn(*args, **kwargs)
    return update


@_serialized_write
def promote_candidate(home: Path | str, candidate: Any, *, liked_only: bool = False) -> dict[str, Any]:
    decision = evaluate_candidate_for_promotion(home, candidate, liked_only=liked_only)
    candidate_id = str(_candidate_value(candidate, "candidate_id", "") or "")
    trait_key = str(_candidate_value(candidate, "trait_key", "") or "")
    layer = str(_candidate_value(candidate, "target_layer", "") or "")
    if not decision.eligible:
        _audit(home, "promotion_deferred", {
            "candidate_id": candidate_id,
            "target_layer": layer,
            "trait_key": trait_key,
            "reason": decision.reason,
            "metrics": decision.metrics,
        })
        return {"status": "deferred", "reason": decision.reason}

    authority = load_personality_authority(home)
    previous = (authority.get(layer) or {}).get(trait_key)
    if f"{layer}/{trait_key}" in authority["user_deleted_traits"] or (
        previous and previous.get("user_edited")
    ):
        return {"status": "deferred", "reason": "user_controlled_trait"}
    record = _record(candidate, decision)
    if previous is not None and all(
        previous.get(key) == value
        for key, value in record.items()
        if key != "promoted_at"
    ):
        return {"status": "unchanged", "layer": layer, "trait_key": trait_key}
    authority[layer][trait_key] = record
    _atomic_write_json(_authority_path(home), authority)
    _audit(
        home,
        "promotion_strengthened" if previous else "promotion_applied",
        {
            "candidate_id": candidate_id,
            "target_layer": layer,
            "trait_key": trait_key,
            "previous": previous,
            "result": record,
        },
    )
    return {"status": "promoted", "layer": layer, "trait_key": trait_key}


def promote_eligible_candidates(home: Path | str, *, liked_only: bool = False) -> dict[str, Any]:
    store = PersonalityCandidateStore(home, liked_only=liked_only)
    results = []
    for candidate in store.list_candidates(status="candidate"):
        if evaluate_candidate_for_promotion(home, candidate, liked_only=liked_only).eligible:
            results.append(promote_candidate(home, candidate, liked_only=liked_only))
    return {
        "promoted_count": sum(1 for row in results if row.get("status") == "promoted"),
        "results": results,
    }


@_serialized_write
def rollback_authoritative_trait(
    home: Path | str,
    *,
    target_layer: str,
    trait_key: str,
    reason: str,
) -> dict[str, Any]:
    if target_layer not in _ALLOWED_LAYERS:
        raise ValueError("unsupported target_layer")
    authority = load_personality_authority(home)
    record = (authority.get(target_layer) or {}).pop(trait_key, None)
    if record is None:
        return {"status": "not_found"}
    candidate_id = str(record.get("candidate_id") or "")
    blocked = list(authority.get("blocked_candidate_ids") or [])
    if candidate_id and candidate_id not in blocked:
        blocked.append(candidate_id)
    authority["blocked_candidate_ids"] = blocked
    authority["history"].append({
        "action": "rollback",
        "target_layer": target_layer,
        "trait_key": trait_key,
        "record": record,
        "reason": str(reason or ""),
        "at": _now_iso(),
    })
    _atomic_write_json(_authority_path(home), authority)
    _audit(home, "promotion_rolled_back", {
        "candidate_id": candidate_id,
        "target_layer": target_layer,
        "trait_key": trait_key,
        "reason": str(reason or ""),
    })
    return {"status": "rolled_back", "candidate_id": candidate_id}


def list_authoritative_traits(home: Path | str) -> list[dict[str, str]]:
    authority = load_personality_authority(home)
    return [
        {"layer": layer, "key": key, "statement": str(record["statement"])}
        for layer in ("stable_core", "relational_self")
        for key, record in sorted(authority[layer].items())
        if isinstance(record, dict) and record.get("statement")
    ]


@_serialized_write
def edit_authoritative_trait(
    home: Path | str, layer: str, key: str, statement: str | None,
) -> None:
    if layer not in _ALLOWED_LAYERS:
        raise ValueError("无效的人格分区")
    if statement is not None and (
        not isinstance(statement, str) or not 1 <= len(statement.strip()) <= 280
    ):
        raise ValueError("人格描述须为 1 到 280 字")
    authority = load_personality_authority(home)
    record = authority[layer].get(key)
    if not isinstance(record, dict):
        raise KeyError(key)
    if statement is None:
        del authority[layer][key]
        authority["user_deleted_traits"].append(f"{layer}/{key}")
    else:
        authority[layer][key] = {**record, "statement": " ".join(statement.split()), "user_edited": True}
    _atomic_write_json(_authority_path(home), authority)


def personality_authority_note(home: Path | str) -> str:
    authority = load_personality_authority(home)
    stable = authority.get("stable_core") or {}
    relational = authority.get("relational_self") or {}
    if not stable and not relational:
        return ""
    lines = [
        "Promoted companion personality context:",
        "Treat these as established companion tendencies, not user facts.",
    ]
    for label, records in (("Stable Core", stable), ("Relational Self", relational)):
        candidates = sorted(
            ((key, row) for key, row in records.items() if isinstance(row, dict)),
            key=lambda item: (not item[1].get("user_edited"), item[0]),
        )
        for _, row in candidates:
            statement = str(row.get("statement") or "").strip()[:280]
            if not statement:
                continue
            line = f"- {label}: {statement}"
            if sum(len(item) + 1 for item in lines) + len(line) > _AUTHORITY_PROMPT_LIMIT:
                break
            lines.append(line)
    return "\n".join(lines)
