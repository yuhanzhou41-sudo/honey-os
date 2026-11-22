"""Frozen contracts for conditional autonomous understanding (U2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class GateAction(StrEnum):
    RUN = "RUN"
    SKIP = "SKIP"
    DEFER = "DEFER"
    BLOCKED = "BLOCKED"


class LabelState(StrEnum):
    TENTATIVE = "tentative"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    WEAKENED = "weakened"
    SUPERSEDED = "superseded"
    RETIRED = "retired"
    NEEDS_REASSESSMENT = "needs_reassessment"
    USER_SUPPRESSED = "user_suppressed"


class EvidenceGrade(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ALLOWED_CATEGORIES = frozenset({
    "interest_preference", "behavior_pattern", "learning_work_style",
    "communication_style", "relationship_style", "value_tendency",
})


@dataclass(frozen=True, slots=True)
class ResolvedModelSpec:
    provider: str
    model: str
    api_mode: str = ""
    config_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not self.provider or not self.model:
            raise ValueError("provider and model are required")


@dataclass(frozen=True, slots=True)
class BatchEnvelope:
    owner_id: str
    lane: str
    namespace: str
    run_id: str
    source_hash: str
    source_revision_digest: str
    completed_at: datetime
    pipeline_version: str = "u2-v1"

    def __post_init__(self) -> None:
        if not all((self.owner_id, self.lane, self.namespace, self.run_id,
                    self.source_hash, self.source_revision_digest)):
            raise ValueError("batch identity and scope must be complete")


@dataclass(frozen=True, slots=True)
class EvidenceUnit:
    ref: str
    source_ref: str
    revision: str
    event_group_id: str
    role: str
    kind: str
    text: str
    scope_keys: tuple[str, ...]
    purposes: frozenset[str]
    original_message_refs: tuple[str, ...] = ()
    independence: str = "unknown"
    occurred_at: datetime | None = None
    time_precision: str = "unknown"

    def __post_init__(self) -> None:
        if not all((self.ref, self.source_ref, self.revision, self.event_group_id)):
            raise ValueError("evidence identity is required")
        if self.role != "user":
            raise ValueError("only user evidence may propose understanding")
        if self.kind in {"assistant", "assistant_inference", "understanding", "model_inference"}:
            raise ValueError("derived model text is not independent user evidence")
        if not self.scope_keys or len(self.text) > 1200:
            raise ValueError("bounded text and controlled scope are required")
        if not self.purposes.issubset({"analysis", "chat", "display", "retrieval"}):
            raise ValueError("unknown purpose")


@dataclass(frozen=True, slots=True)
class GateDecision:
    action: GateAction
    reason: str
    evidence_refs: tuple[str, ...] = ()
    label_refs: tuple[str, ...] = ()
    all_reasons: tuple[str, ...] = ()
    policy_version: str = "u2-policy-v1"


@dataclass(frozen=True, slots=True)
class Proposal:
    operation: str
    category_id: str
    scope_key: str
    canonical_key: str
    text: str
    support_refs: tuple[str, ...] = ()
    counter_refs: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], allowed_refs: set[str],
                     allowed_scopes: set[str]) -> "Proposal":
        allowed = {"operation", "category_id", "scope_key", "canonical_key",
                   "text", "support_refs", "counter_refs"}
        if set(value) - allowed:
            raise ValueError("proposal contains forbidden fields")
        item = cls(
            operation=str(value.get("operation", "")),
            category_id=str(value.get("category_id", "")),
            scope_key=str(value.get("scope_key", "")),
            canonical_key=str(value.get("canonical_key", "")),
            text=str(value.get("text", "")).strip(),
            support_refs=tuple(map(str, value.get("support_refs", ()))),
            counter_refs=tuple(map(str, value.get("counter_refs", ()))),
        )
        if item.operation not in {"propose", "support", "counter", "supersede"}:
            raise ValueError("unsupported operation")
        if item.category_id not in ALLOWED_CATEGORIES:
            raise ValueError("uncontrolled category")
        if item.scope_key not in allowed_scopes or not item.canonical_key or not item.text:
            raise ValueError("invalid scope/key/text")
        if len(item.text) > 360 or len(item.support_refs) + len(item.counter_refs) > 12:
            raise ValueError("proposal exceeds bounds")
        if not set(item.support_refs + item.counter_refs).issubset(allowed_refs):
            raise ValueError("proposal cites unknown evidence")
        return item


@dataclass(frozen=True, slots=True)
class ContextSegment:
    segment_id: str
    source_ref: str
    revision: str
    kind: str
    authority: str
    text: str
    token_cost: int
    policy_epoch: int
    purposes: frozenset[str] = field(default_factory=lambda: frozenset({"chat"}))

    def __post_init__(self) -> None:
        if not self.segment_id or not self.source_ref or self.token_cost < 0:
            raise ValueError("invalid context segment")
