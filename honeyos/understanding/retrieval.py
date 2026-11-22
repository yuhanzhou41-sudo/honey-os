"""Bounded T/K/A metadata ranking for understanding recall shadow mode.

The caller owns lexical/topic matching and source resolution. This module only
normalizes already-authorized metadata candidates, applies bounded ranking,
deduplicates original evidence, and enforces one shared result/character budget.
It never reads a source body or calls a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
from math import exp
from typing import Iterable

from .contracts import MemorySourceRef, RecallCandidate, RecallScoreBreakdown

MAX_INPUTS = 100
MAX_RESULTS = 6
MAX_CHAR_BUDGET = 1200
MAX_STATE_BIAS = 0.15


@dataclass(frozen=True, slots=True)
class RecallSeed:
    source: MemorySourceRef
    label_id: str
    topic_score: float
    salience: float = 0.0
    char_cost: int = 0
    hop: int = 0

    def __post_init__(self) -> None:
        if not self.label_id:
            raise ValueError("label_id must be nonempty")
        if self.hop not in {0, 1}:
            raise ValueError("only direct and one-hop candidates are allowed")
        if self.char_cost < 0:
            raise ValueError("char_cost must be nonnegative")


@dataclass(frozen=True, slots=True)
class RejectedRecall:
    source_system: str
    source_record_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class RecallShadowResult:
    selected: tuple[RecallCandidate, ...]
    rejected: tuple[RejectedRecall, ...]
    total_char_cost: int
    input_count: int
    model_calls: int = 0
    prompt_injection: bool = False

    @property
    def metrics(self) -> dict[str, int | bool]:
        return {
            "input_count": self.input_count,
            "selected_count": len(self.selected),
            "rejected_count": len(self.rejected),
            "total_char_cost": self.total_char_cost,
            "model_calls": self.model_calls,
            "prompt_injection": self.prompt_injection,
        }


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _temporal_score(source: MemorySourceRef, now: datetime) -> tuple[float, str]:
    """Return a small recency feature without inventing missing dates."""
    occurred = _aware(source.occurred_at)
    created = _aware(source.created_at)
    anchor = occurred or created
    if anchor is None:
        return 0.0, "time_unknown"
    age_days = max(0.0, (now - anchor).total_seconds() / 86400.0)
    # Half-life is approximately 180 days and the whole time dimension is
    # capped below topic relevance. Historical recall therefore remains
    # possible instead of being erased by recency.
    score = 0.20 * exp(-age_days / 260.0)
    return score, "time_occurred" if occurred else "time_created"


def _message_groups(source: MemorySourceRef) -> set[str]:
    if source.source_session_id and source.source_message_ids:
        return {
            f"message:{source.owner}:{source.source_session_id}:{message_id}"
            for message_id in source.source_message_ids
        }
    return {source.evidence_group}


class ThreeDimensionalRecallRanker:
    """Rank authorized headers by topic, time, salience, and bounded state.

    `state_bias_by_label` must contain a normalized, current Honey-state view.
    Bias is ignored for candidates with no positive topic match and cannot
    affect source permission, validity, or deduplication.
    """

    def __init__(self, *, max_inputs: int = 36, max_results: int = 3,
                 char_budget: int = 700) -> None:
        self.max_inputs = min(MAX_INPUTS, max(1, int(max_inputs)))
        self.max_results = min(MAX_RESULTS, max(1, int(max_results)))
        self.char_budget = min(MAX_CHAR_BUDGET, max(0, int(char_budget)))

    def rank(
        self,
        seeds: Iterable[RecallSeed],
        *,
        purpose: str,
        now: datetime | None = None,
        state_bias_by_label: dict[str, float] | None = None,
    ) -> RecallShadowResult:
        if purpose not in {"retrieval", "analysis", "chat"}:
            return RecallShadowResult((), (), 0, 0)
        clock = _aware(now) or datetime.now(timezone.utc)
        state_bias_by_label = state_bias_by_label or {}
        # Inspect one extra header to report truncation without traversing a
        # large or unbounded provider iterator.
        materialized = list(islice(seeds, self.max_inputs + 1))
        input_count = len(materialized)
        rejected: list[RejectedRecall] = []
        ranked: list[RecallCandidate] = []

        for seed in materialized[:self.max_inputs]:
            source = seed.source
            reject = lambda reason: rejected.append(RejectedRecall(
                source.source_system, source.source_record_id, reason,
            ))
            if not source.permits(purpose):
                reject("permission_denied")
                continue
            valid_from = _aware(source.valid_from)
            valid_to = _aware(source.valid_to)
            if valid_from and clock < valid_from:
                reject("not_yet_valid")
                continue
            if valid_to and clock >= valid_to:
                reject("expired")
                continue
            topic = _clamp(seed.topic_score, 0.0, 1.0)
            if seed.hop == 1:
                topic *= 0.65
            if topic <= 0.0:
                reject("topic_mismatch")
                continue
            temporal, time_reason = _temporal_score(source, clock)
            salience = 0.20 * _clamp(seed.salience, 0.0, 1.0)
            state = _clamp(
                state_bias_by_label.get(seed.label_id, 0.0),
                -MAX_STATE_BIAS,
                MAX_STATE_BIAS,
            )
            breakdown = RecallScoreBreakdown(topic, temporal, salience, state)
            reasons = ["topic_direct" if seed.hop == 0 else "topic_one_hop", time_reason]
            if salience:
                reasons.append("source_salience")
            if state:
                reasons.append("state_bounded")
            ranked.append(RecallCandidate(
                source=source, label_id=seed.label_id,
                score=round(breakdown.total, 6), char_cost=seed.char_cost,
                breakdown=breakdown, reason_codes=tuple(reasons), hop=seed.hop,
            ))

        if input_count > self.max_inputs:
            seed = materialized[self.max_inputs]
            rejected.append(RejectedRecall(
                seed.source.source_system, seed.source.source_record_id,
                "input_limit",
            ))

        ranked.sort(key=lambda item: (
            -item.score,
            _aware(item.source.occurred_at) or _aware(item.source.created_at)
            or datetime.min.replace(tzinfo=timezone.utc),
            item.source.source_system,
            item.source.source_record_id,
        ), reverse=False)

        selected: list[RecallCandidate] = []
        groups: set[str] = set()
        total = 0
        for candidate in ranked:
            source_groups = _message_groups(candidate.source)
            if source_groups & groups:
                rejected.append(RejectedRecall(
                    candidate.source.source_system,
                    candidate.source.source_record_id,
                    "duplicate_evidence",
                ))
                continue
            if len(selected) >= self.max_results:
                rejected.append(RejectedRecall(
                    candidate.source.source_system,
                    candidate.source.source_record_id,
                    "result_limit",
                ))
                continue
            if total + candidate.char_cost > self.char_budget:
                rejected.append(RejectedRecall(
                    candidate.source.source_system,
                    candidate.source.source_record_id,
                    "char_budget",
                ))
                continue
            groups.update(source_groups)
            selected.append(candidate)
            total += candidate.char_cost

        return RecallShadowResult(
            selected=tuple(selected), rejected=tuple(rejected[:100]),
            total_char_cost=total, input_count=input_count,
        )
