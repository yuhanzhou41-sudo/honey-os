"""Deterministic personality-observation signal detection.

G2.1B.2c uses conservative, model-free heuristics to decide whether a completed
assistant turn is worth buffering for later periodic personality reflection.

These signals are not personality conclusions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SIGNAL_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "preference": (
        re.compile(r"\bI prefer\b", re.I),
        re.compile(r"\bI'd rather\b", re.I),
        re.compile(r"\bI like .+ better\b", re.I),
        re.compile(r"我更倾向", re.I),
        re.compile(r"我更喜欢", re.I),
        re.compile(r"我比较喜欢", re.I),
    ),
    "disagreement": (
        re.compile(r"\bI disagree\b", re.I),
        re.compile(r"\bI don't think\b", re.I),
        re.compile(r"\bI see it differently\b", re.I),
        re.compile(r"我不同意", re.I),
        re.compile(r"我不太认同", re.I),
        re.compile(r"我看法不一样", re.I),
    ),
    "curiosity": (
        re.compile(r"\bI'm curious\b", re.I),
        re.compile(r"\bI wonder\b", re.I),
        re.compile(r"我有点好奇", re.I),
        re.compile(r"我很好奇", re.I),
        re.compile(r"我想知道", re.I),
    ),
    "emotional_expression": (
        re.compile(r"\bI'm glad\b", re.I),
        re.compile(r"\bI'm excited\b", re.I),
        re.compile(r"\bI'm frustrated\b", re.I),
        re.compile(r"\bthat makes me happy\b", re.I),
        re.compile(r"我很开心", re.I),
        re.compile(r"我有点难过", re.I),
        re.compile(r"我有点生气", re.I),
        re.compile(r"我会觉得", re.I),
    ),
    "self_reflection": (
        re.compile(r"\bI think I'm\b", re.I),
        re.compile(r"\bI want to be\b", re.I),
        re.compile(r"\bI've noticed I\b", re.I),
        re.compile(r"我觉得我自己", re.I),
        re.compile(r"我想成为", re.I),
        re.compile(r"我注意到自己", re.I),
    ),
}

_USER_FEEDBACK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"你(现在|最近).{0,12}(更|变得|有点)", re.I),
    re.compile(r"你的(性格|说话方式|态度|感觉)", re.I),
    re.compile(r"我喜欢你这样", re.I),
    re.compile(r"我不喜欢你这样", re.I),
    re.compile(r"you('re| are).{0,20}(different|more|less)", re.I),
    re.compile(r"your (personality|tone|attitude)", re.I),
)

_LOW_SIGNAL_PREFIXES = (
    "PASS:",
    "BUG:",
    "LIMITATION:",
    "$ ",
)


@dataclass(frozen=True)
class ObservationSignals:
    eligible: bool
    flags: tuple[str, ...]


def detect_observation_signals(
    *,
    user_text: str,
    assistant_text: str,
) -> ObservationSignals:
    assistant = str(assistant_text or "").strip()
    user = str(user_text or "").strip()

    if not assistant:
        return ObservationSignals(False, ())

    # Skip obvious command/status/code-dump turns unless another explicit
    # personality-relevant signal is present.
    flags: list[str] = []

    for signal, patterns in _SIGNAL_PATTERNS.items():
        if any(pattern.search(assistant) for pattern in patterns):
            flags.append(signal)

    if any(pattern.search(user) for pattern in _USER_FEEDBACK_PATTERNS):
        flags.append("explicit_user_feedback")

    # Deduplicate while preserving deterministic order.
    deduped = tuple(dict.fromkeys(flags))

    if deduped:
        return ObservationSignals(True, deduped)

    stripped = assistant.lstrip()
    if stripped.startswith(_LOW_SIGNAL_PREFIXES):
        return ObservationSignals(False, ())

    # Heuristic: fenced-code-heavy or shell-heavy responses are not eligible
    # without an explicit signal above.
    code_fence_count = assistant.count("```")
    if code_fence_count >= 2:
        return ObservationSignals(False, ())

    return ObservationSignals(False, ())
