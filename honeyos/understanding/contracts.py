"""Small, immutable read models shared by future understanding adapters.

Permission flags describe the source's current grant. Derived objects may
only narrow that grant; they cannot grant chat access to a source themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MemoryKind(StrEnum):
    IDENTITY_FACT = "identity_fact"
    SELF_REPORT = "self_report"
    LONG_TERM_FACT = "long_term_fact"
    RECENT_CHAPTER = "recent_chapter"
    EPISODE = "episode"
    OPEN_LOOP = "open_loop"
    TEMPORARY_STATE = "temporary_state"
    COMMITMENT = "commitment"
    UNDERSTANDING_LABEL = "understanding_label"


class TimePrecision(StrEnum):
    UNKNOWN = "unknown"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    INSTANT = "instant"


class FactAuthority(StrEnum):
    SELF_REPORTED = "self_reported"
    NATIVE_OBSERVED = "native_observed"
    EXTERNALLY_VERIFIED = "externally_verified"


class PrivacyLevel(StrEnum):
    GENERAL = "general"
    PRIVATE = "private"
    SENSITIVE = "sensitive"


@dataclass(frozen=True, slots=True)
class MemorySourceRef:
    source_system: str
    source_record_id: str
    owner: str
    lane: str
    namespace: str
    revision: str
    kind: MemoryKind
    retrievable: bool
    chat_allowed: bool
    analysis_allowed: bool
    source_session_id: str = ""
    source_message_ids: tuple[int, ...] = ()
    source_hash: str = ""
    occurred_at: datetime | None = None
    time_precision: TimePrecision = TimePrecision.UNKNOWN
    created_at: datetime | None = None
    last_recalled_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    revoked: bool = False

    def __post_init__(self) -> None:
        if not all((self.source_system, self.source_record_id, self.owner, self.lane,
                    self.namespace, self.revision)):
            raise ValueError("source identity and scope must be nonempty")
        if any(item <= 0 for item in self.source_message_ids):
            raise ValueError("message ids must be positive")
        if self.time_precision != TimePrecision.UNKNOWN and self.occurred_at is None:
            raise ValueError("time precision requires occurred_at")
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("valid_from must not follow valid_to")

    @property
    def evidence_group(self) -> str:
        """Collapse summaries of the same original messages into one group."""
        if self.source_session_id and self.source_message_ids:
            ids = ",".join(str(item) for item in sorted(set(self.source_message_ids)))
            return f"message:{self.owner}:{self.source_session_id}:{ids}"
        if self.source_hash:
            return f"hash:{self.owner}:{self.source_hash}"
        return f"record:{self.owner}:{self.source_system}:{self.source_record_id}"

    def permits(self, purpose: str) -> bool:
        if self.revoked or not self.retrievable:
            return False
        return {
            "retrieval": True,
            "chat": self.chat_allowed,
            "analysis": self.analysis_allowed,
        }.get(purpose, False)


@dataclass(frozen=True, slots=True)
class PersonalFactRef:
    """Metadata-only reference to a fact value held by its source store."""

    predicate: str
    value_ref: str
    source: MemorySourceRef
    authority: FactAuthority
    privacy_level: PrivacyLevel

    def __post_init__(self) -> None:
        if not self.predicate or not self.value_ref:
            raise ValueError("predicate and value_ref must be nonempty")

    def visible_for(self, purpose: str, *, include_sensitive: bool = False) -> bool:
        if self.privacy_level == PrivacyLevel.SENSITIVE and not include_sensitive:
            return False
        return self.source.permits(purpose)


@dataclass(frozen=True, slots=True)
class TopicHeader:
    topic_id: str
    owner: str
    namespace: str
    name: str
    revision: int


@dataclass(frozen=True, slots=True)
class LabelHeader:
    label_id: str
    topic_id: str
    owner: str
    namespace: str
    summary: str
    status: str
    revision: int


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    label_id: str
    source: MemorySourceRef
    relation: str


@dataclass(frozen=True, slots=True)
class RecallScoreBreakdown:
    topic: float
    temporal: float
    salience: float
    state_bias: float

    @property
    def total(self) -> float:
        return self.topic + self.temporal + self.salience + self.state_bias


@dataclass(frozen=True, slots=True)
class RecallCandidate:
    source: MemorySourceRef
    label_id: str
    score: float
    char_cost: int
    breakdown: RecallScoreBreakdown | None = None
    reason_codes: tuple[str, ...] = ()
    hop: int = 0

    def __post_init__(self) -> None:
        if self.char_cost < 0:
            raise ValueError("char_cost must be nonnegative")
        if self.hop not in {0, 1}:
            raise ValueError("recall candidates may be at most one hop away")
