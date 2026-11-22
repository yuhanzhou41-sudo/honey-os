"""Source-aware user understanding contracts.

This package does not perform retrieval or alter existing memory stores.
"""

from .contracts import (
    EvidenceLink,
    FactAuthority,
    LabelHeader,
    MemoryKind,
    MemorySourceRef,
    PersonalFactRef,
    PrivacyLevel,
    RecallCandidate,
    RecallScoreBreakdown,
    TimePrecision,
    TopicHeader,
)

__all__ = [
    "EvidenceLink",
    "FactAuthority",
    "LabelHeader",
    "MemoryKind",
    "MemorySourceRef",
    "PersonalFactRef",
    "PrivacyLevel",
    "RecallCandidate",
    "RecallScoreBreakdown",
    "TimePrecision",
    "TopicHeader",
]
