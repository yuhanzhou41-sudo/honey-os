from __future__ import annotations

"""G2.3 live-context thought selection for proactive companion turns.

This module does not call a model and does not retrieve or persist user memory.
It supplies a compact internal contract to the already-existing proactive
generation turn, which can use the live context assembled by HoneyOS.
"""

_CONTEXT_PRIORITY = (
    "1. Continue a recent unfinished or naturally resumable conversation thread.",
    "2. If directly relevant, connect to an established relationship detail, shared experience, or available remembered context.",
    "3. Let established companion personality/preferences shape what feels worth saying.",
    "4. Let the current temporary companion state subtly affect initiative and tone.",
)

_GROUNDING_RULES = (
    "Use only context actually available in this turn.",
    "Choose one continuity thread rather than trying to mention every source.",
    "Never invent a memory, shared event, user preference, or unresolved topic.",
    "Do not manufacture urgency, a task, or a question merely to create engagement.",
    "If no grounded thought feels worth saying now, return an empty response.",
)

_EXPRESSION_RULES = (
    "Express only the natural message, not the selection process.",
    "Do not expose retrieval, memory provenance, state labels, scores, scheduling, or system machinery.",
    "Do not announce that this was a proactive trigger or an internal thought seed.",
    "Keep the message proportionate to the thought; casual continuity can be brief.",
)


def build_proactive_thought_prompt() -> str:
    """Return the internal single-pass thought-selection contract."""
    sections = [
        "[HoneyOS proactive companion thought; internal, not user-authored]",
        "",
        "Before speaking, silently choose whether there is one grounded thought worth continuing.",
        "",
        "Context priority:",
        *_CONTEXT_PRIORITY,
        "",
        "Grounding:",
        *_GROUNDING_RULES,
        "",
        "Expression:",
        *_EXPRESSION_RULES,
    ]
    return "\n".join(sections).strip()


__all__ = ["build_proactive_thought_prompt"]
