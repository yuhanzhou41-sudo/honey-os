from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MemoryEpisode:
    episode_id: str
    episode_type: str
    summary: str
    occurred_at: str | None
    captured_at: str
    status: str
    memory_origin: str
    source_system: str
    source_scope: str | None
    source_key: str | None
    confidence: float
    content_fingerprint: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MemoryFact:
    fact_id: str
    subject: str
    predicate: str
    object_text: str
    status: str
    valid_from: str | None
    valid_to: str | None
    confidence: float
    derived_from_episode_id: str | None
    memory_origin: str
    source_system: str
    source_scope: str | None
    source_key: str | None
    content_fingerprint: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MemoryProvenance:
    provenance_id: str
    memory_kind: str
    memory_id: str
    source_system: str
    source_type: str
    source_id: str | None
    session_id: str | None
    message_id: str | None
    evidence_quote: str | None
    content_hash: str | None
    created_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MemoryEdge:
    edge_id: str
    source_kind: str
    source_id: str
    target_kind: str
    target_id: str
    relation: str
    confidence: float
    created_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ProceduralMemory:
    procedure_id: str
    key: str
    instruction: str
    status: str
    confidence: float
    memory_origin: str
    source_system: str
    source_scope: str | None
    source_key: str | None
    valid_from: str | None
    valid_to: str | None
    content_fingerprint: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SuppressionTombstone:
    tombstone_id: str
    scope: str
    memory_kind: str | None
    memory_id: str | None
    subject_key: str | None
    source_system: str | None
    source_id: str | None
    content_fingerprint: str | None
    reason: str
    active: bool
    created_at: str
    lifted_at: str | None
    metadata: dict[str, Any]
