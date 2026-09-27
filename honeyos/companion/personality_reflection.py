"""Periodic personality reflection runner for HoneyOS companion mode.

G2.1B.2b:
- batches pending observations,
- calls an injected reflection adapter,
- validates strict structured JSON,
- applies Candidate Store mutations atomically at the runner level,
- marks the reviewed observation batch processed only after a successful apply.

This module does not connect to chat runtime, scheduling, prompt assembly, or
authoritative personality persistence.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from honeyos.companion.personality_candidates import PersonalityCandidateStore

ReflectionAdapter = Callable[[dict[str, Any]], Any]

_ALLOWED_ACTIONS = {"create", "support", "contradict", "none"}
_ALLOWED_LAYERS = {"relational_self", "stable_core"}
_RESERVED_TRAIT_KEYS = {
    "name",
    "companion_name",
    "assistant_name",
    "display_name",
    "user_nickname",
    "relationship",
    "boundaries",
    "tool_permissions",
    "safety_policy",
    "credentials",
    "account_identity",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _normalize_trait_key(value: object) -> str:
    text = str(value or "").strip().lower()
    normalized = "".join(ch if ch.isalnum() else "_" for ch in text)
    normalized = "_".join(part for part in normalized.split("_") if part)
    if not normalized:
        raise ValueError("trait_key must not be empty")
    if normalized in _RESERVED_TRAIT_KEYS:
        raise ValueError(f"trait_key is outside personality formation: {normalized}")
    return normalized


def _bounded_confidence(value: object) -> float:
    confidence = float(value)
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("confidence must be between 0 and 1")
    return round(confidence, 6)


@dataclass(frozen=True)
class ReflectionPolicy:
    count_trigger: int = 20
    age_trigger_hours: int = 24
    age_trigger_min_count: int = 5
    min_automatic_interval_hours: int = 12
    batch_limit: int = 50


@dataclass(frozen=True)
class ReflectionDecision:
    should_reflect: bool
    reason: str
    pending_count: int


@dataclass(frozen=True)
class ReflectionRunResult:
    status: str
    batch_id: str
    observation_count: int
    operation_count: int
    error: str = ""


class PersonalityReflectionRunner:
    def __init__(
        self,
        home: Path | str,
        *,
        adapter: ReflectionAdapter,
        policy: ReflectionPolicy | None = None,
        now_fn: Callable[[], datetime] = _utcnow,
    ):
        self.store = PersonalityCandidateStore(home)
        self.adapter = adapter
        self.policy = policy or ReflectionPolicy()
        self.now_fn = now_fn
        self.state_path = self.store.root / "personality_reflection_state.json"

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {
                "last_attempt_at": "",
                "last_success_at": "",
                "last_batch_id": "",
                "last_observation_count": 0,
                "last_error": "",
            }
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_state(self, state: Mapping[str, Any]) -> None:
        self.store.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_attempt_at": str(state.get("last_attempt_at") or ""),
            "last_success_at": str(state.get("last_success_at") or ""),
            "last_batch_id": str(state.get("last_batch_id") or ""),
            "last_observation_count": int(state.get("last_observation_count") or 0),
            "last_error": str(state.get("last_error") or "")[:2000],
        }
        self.state_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def should_reflect(self, *, force: bool = False) -> ReflectionDecision:
        pending = self.store.pending_observation_count()
        if force:
            return ReflectionDecision(
                should_reflect=pending > 0,
                reason="forced" if pending > 0 else "no_pending_observations",
                pending_count=pending,
            )

        if pending <= 0:
            return ReflectionDecision(False, "no_pending_observations", 0)

        now = self.now_fn()
        state = self._load_state()
        last_success = _parse_iso(str(state.get("last_success_at") or ""))

        if last_success is not None:
            min_interval = timedelta(hours=self.policy.min_automatic_interval_hours)
            if now - last_success < min_interval:
                return ReflectionDecision(
                    False,
                    "rate_limited",
                    pending,
                )

        if pending >= self.policy.count_trigger:
            return ReflectionDecision(True, "count_trigger", pending)

        if pending >= self.policy.age_trigger_min_count:
            oldest_rows = self.store.list_pending_observations(limit=1)
            if oldest_rows:
                oldest = _parse_iso(str(oldest_rows[0].get("observed_at") or ""))
                if oldest is not None:
                    age = now - oldest
                    if age >= timedelta(hours=self.policy.age_trigger_hours):
                        return ReflectionDecision(True, "age_trigger", pending)

        return ReflectionDecision(False, "below_threshold", pending)

    def _build_batch(self) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        observations = self.store.list_pending_observations(
            limit=self.policy.batch_limit
        )
        batch_id = uuid.uuid4().hex
        payload = {
            "batch_id": batch_id,
            "observations": [
                {
                    "observation_id": row["observation_id"],
                    "observed_at": row["observed_at"],
                    "signal_flags": list(row.get("signal_flags") or []),
                    "user_excerpt": str(row.get("user_excerpt") or ""),
                    "assistant_excerpt": str(row.get("assistant_excerpt") or ""),
                }
                for row in observations
            ],
        }
        return batch_id, observations, payload

    @staticmethod
    def _coerce_adapter_output(raw: Any) -> dict[str, Any]:
        if isinstance(raw, str):
            data = json.loads(raw)
        elif isinstance(raw, Mapping):
            data = dict(raw)
        else:
            raise ValueError("reflection adapter must return JSON string or mapping")

        if set(data.keys()) != {"operations"}:
            raise ValueError("reflection result must contain only operations")
        if not isinstance(data["operations"], list):
            raise ValueError("operations must be a list")
        return data

    @staticmethod
    def _validate_operations(
        payload: Mapping[str, Any],
        *,
        allowed_observation_ids: set[str],
    ) -> list[dict[str, Any]]:
        validated: list[dict[str, Any]] = []

        for index, raw in enumerate(payload["operations"]):
            if not isinstance(raw, Mapping):
                raise ValueError(f"operation {index} must be an object")

            allowed_keys = {
                "action",
                "target_layer",
                "trait_key",
                "statement",
                "confidence",
                "evidence_observation_ids",
            }
            extra = set(raw) - allowed_keys
            if extra:
                raise ValueError(
                    f"operation {index} contains unsupported fields: {sorted(extra)}"
                )

            action = str(raw.get("action") or "").strip()
            if action not in _ALLOWED_ACTIONS:
                raise ValueError(f"unsupported action: {action}")

            if action == "none":
                evidence_ids = raw.get("evidence_observation_ids") or []
                if evidence_ids:
                    raise ValueError("none operation cannot reference evidence")
                validated.append({"action": "none"})
                continue

            target_layer = str(raw.get("target_layer") or "").strip()
            if target_layer not in _ALLOWED_LAYERS:
                raise ValueError(f"unsupported target_layer: {target_layer}")

            trait_key = _normalize_trait_key(raw.get("trait_key"))
            statement = str(raw.get("statement") or "").strip()
            if not statement:
                raise ValueError("statement must not be empty")
            if len(statement) > 800:
                raise ValueError("statement exceeds 800 characters")

            confidence = _bounded_confidence(raw.get("confidence", 0.5))

            evidence_ids = raw.get("evidence_observation_ids")
            if not isinstance(evidence_ids, list) or not evidence_ids:
                raise ValueError("evidence_observation_ids must be a non-empty list")

            clean_ids: list[str] = []
            for value in evidence_ids:
                observation_id = str(value or "").strip()
                if not observation_id:
                    raise ValueError("empty evidence observation id")
                if observation_id not in allowed_observation_ids:
                    raise ValueError(
                        f"evidence observation is outside batch: {observation_id}"
                    )
                if observation_id not in clean_ids:
                    clean_ids.append(observation_id)

            validated.append(
                {
                    "action": action,
                    "target_layer": target_layer,
                    "trait_key": trait_key,
                    "statement": statement,
                    "confidence": confidence,
                    "evidence_observation_ids": clean_ids,
                }
            )

        return validated

    def _find_active_candidate(
        self,
        *,
        target_layer: str,
        trait_key: str,
    ):
        for candidate in self.store.list_candidates(
            status="candidate",
            target_layer=target_layer,
        ):
            if candidate.trait_key == trait_key:
                return candidate
        return None

    def _preflight_operations(
        self,
        operations: Sequence[Mapping[str, Any]],
    ) -> None:
        active: set[tuple[str, str]] = {
            (candidate.target_layer, candidate.trait_key)
            for candidate in self.store.list_candidates(status="candidate")
        }

        for operation in operations:
            action = operation["action"]
            if action == "none":
                continue

            key = (
                str(operation["target_layer"]),
                str(operation["trait_key"]),
            )

            if action == "create":
                if key in active:
                    raise ValueError(
                        f"create requires no active candidate: {key[0]}/{key[1]}"
                    )
                active.add(key)
                continue

            if action in {"support", "contradict"}:
                if key not in active:
                    raise ValueError(
                        f"{action} requires an active candidate: {key[0]}/{key[1]}"
                    )
                continue

            raise ValueError(f"unsupported action: {action}")

    def _apply_operations(
        self,
        operations: Sequence[Mapping[str, Any]],
        observations_by_id: Mapping[str, Mapping[str, Any]],
    ) -> int:
        applied = 0

        for operation in operations:
            action = operation["action"]
            if action == "none":
                continue

            target_layer = str(operation["target_layer"])
            trait_key = str(operation["trait_key"])
            statement = str(operation["statement"])
            confidence = float(operation["confidence"])
            evidence_ids = list(operation["evidence_observation_ids"])

            evidence_summaries = []
            for observation_id in evidence_ids:
                row = observations_by_id[observation_id]
                assistant_excerpt = str(row.get("assistant_excerpt") or "").strip()
                user_excerpt = str(row.get("user_excerpt") or "").strip()
                summary = assistant_excerpt or user_excerpt or "Observed interaction signal."
                signal_flags = set(row.get("signal_flags") or [])
                evidence_type = (
                    "user_feedback"
                    if signal_flags == {"explicit_user_feedback"}
                    else "self_observation"
                )
                evidence_summaries.append((observation_id, summary, evidence_type))

            if action == "create":
                first_id, first_summary, first_type = evidence_summaries[0]
                candidate = self.store.create_candidate(
                    target_layer=target_layer,
                    trait_key=trait_key,
                    statement=statement,
                    confidence=confidence,
                    evidence_summary=first_summary,
                    evidence_reference=first_id,
                    origin=first_type,
                )
                for observation_id, summary, evidence_type in evidence_summaries[1:]:
                    candidate = self.store.add_evidence(
                        candidate.candidate_id,
                        evidence_type=evidence_type,
                        summary=summary,
                        reference=observation_id,
                    )
                applied += 1
                continue

            candidate = self._find_active_candidate(
                target_layer=target_layer,
                trait_key=trait_key,
            )
            if candidate is None:
                raise ValueError(
                    f"{action} requires an active candidate: {target_layer}/{trait_key}"
                )

            if action == "support":
                for observation_id, summary, evidence_type in evidence_summaries:
                    candidate = self.store.add_evidence(
                        candidate.candidate_id,
                        evidence_type=evidence_type,
                        summary=summary,
                        reference=observation_id,
                    )
                applied += 1
                continue

            if action == "contradict":
                for observation_id, summary, evidence_type in evidence_summaries:
                    candidate = self.store.record_contradiction(
                        candidate.candidate_id,
                        summary=summary,
                        reference=observation_id,
                    )
                applied += 1
                continue

            raise ValueError(f"unsupported action: {action}")

        return applied

    def run_once(self, *, force: bool = False) -> ReflectionRunResult:
        decision = self.should_reflect(force=force)
        if not decision.should_reflect:
            return ReflectionRunResult(
                status="skipped",
                batch_id="",
                observation_count=decision.pending_count,
                operation_count=0,
                error=decision.reason,
            )

        batch_id, observations, adapter_payload = self._build_batch()
        now = self.now_fn()
        state = self._load_state()
        state.update(
            {
                "last_attempt_at": _iso(now),
                "last_batch_id": batch_id,
                "last_observation_count": len(observations),
                "last_error": "",
            }
        )
        self._save_state(state)
        self.store._audit(
            "reflection_started",
            {
                "batch_id": batch_id,
                "observation_count": len(observations),
            },
        )

        try:
            raw = self.adapter(adapter_payload)
            parsed = self._coerce_adapter_output(raw)
            allowed_ids = {row["observation_id"] for row in observations}
            operations = self._validate_operations(
                parsed,
                allowed_observation_ids=allowed_ids,
            )

            observations_by_id = {
                row["observation_id"]: row
                for row in observations
            }

            # Validate business dependencies before any Candidate Store mutation.
            self._preflight_operations(operations)
            operation_count = self._apply_operations(
                operations,
                observations_by_id,
            )

            self.store.mark_observations_processed(
                [row["observation_id"] for row in observations],
                reflection_batch_id=batch_id,
                processed_at=_iso(now),
            )

            state.update(
                {
                    "last_success_at": _iso(now),
                    "last_error": "",
                }
            )
            self._save_state(state)
            self.store._audit(
                "reflection_succeeded",
                {
                    "batch_id": batch_id,
                    "observation_count": len(observations),
                    "operation_count": operation_count,
                },
            )
            return ReflectionRunResult(
                status="success",
                batch_id=batch_id,
                observation_count=len(observations),
                operation_count=operation_count,
            )

        except Exception as exc:
            state.update({"last_error": str(exc)})
            self._save_state(state)
            self.store._audit(
                "reflection_failed",
                {
                    "batch_id": batch_id,
                    "observation_count": len(observations),
                    "error": str(exc)[:1000],
                },
            )
            return ReflectionRunResult(
                status="failed",
                batch_id=batch_id,
                observation_count=len(observations),
                operation_count=0,
                error=str(exc),
            )
