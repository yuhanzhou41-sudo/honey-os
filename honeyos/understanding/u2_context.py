"""One bounded memory composer shared by supported front doors."""

from __future__ import annotations

from dataclasses import dataclass

from .u2_contracts import ContextSegment


@dataclass(frozen=True, slots=True)
class ComposedContext:
    text: str
    segment_ids: tuple[str, ...]
    token_cost: int
    truncated: bool


UNDERSTANDING_BEGIN = "<!-- honeyos-understanding-v2:begin -->"
UNDERSTANDING_END = "<!-- honeyos-understanding-v2:end -->"


def wrap_understanding(text: str) -> str:
    """Mark derived text so persisted sidecars can be revoked safely."""
    if not text:
        return ""
    return (f"{UNDERSTANDING_BEGIN}\n"
            "Honey 的以下内容是有限、可能不准确且仅适用于所述范围的理解；"
            "它不是已验证事实。支持与反证应同时考虑。\n"
            f"{text}\n{UNDERSTANDING_END}")


def strip_understanding(text: str) -> str:
    """Remove only complete U2 blocks; fail closed on a malformed marker."""
    if not isinstance(text, str) or UNDERSTANDING_BEGIN not in text:
        return text
    output = text
    while UNDERSTANDING_BEGIN in output:
        start = output.find(UNDERSTANDING_BEGIN)
        end = output.find(UNDERSTANDING_END, start)
        if end < 0:
            return output[:start].rstrip()
        output = (output[:start] + output[end + len(UNDERSTANDING_END):]).strip()
    return output


def compose_memory_context(segments: tuple[ContextSegment, ...], *, total_budget: int,
                           graph_budget: int = 1750, current_policy_epoch: int,
                           purpose: str = "chat") -> ComposedContext:
    if total_budget < 0:
        raise ValueError("budget must be nonnegative")
    selected: list[ContextSegment] = []
    seen_sources: set[tuple[str, str]] = set()
    used = graph_used = 0
    truncated = False
    # caller order expresses authority/relevance; stable source+revision removes
    # exact duplicates without guessing semantic equivalence.
    for item in segments:
        if purpose not in item.purposes or item.policy_epoch != current_policy_epoch:
            continue
        identity = (item.source_ref, item.revision)
        if identity in seen_sources:
            continue
        if item.kind == "understanding" and graph_used + item.token_cost > graph_budget:
            truncated = True
            continue
        if used + item.token_cost > total_budget:
            truncated = True
            continue
        seen_sources.add(identity)
        selected.append(item)
        used += item.token_cost
        if item.kind == "understanding":
            graph_used += item.token_cost
    blocks = []
    for item in selected:
        if not item.text:
            continue
        blocks.append(wrap_understanding(item.text)
                      if item.kind == "understanding" else item.text)
    text = "\n\n".join(blocks)
    return ComposedContext(text, tuple(item.segment_id for item in selected), used, truncated)

