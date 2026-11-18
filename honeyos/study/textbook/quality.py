"""Collection quality gate: reject obviously broken section text before caching."""

from __future__ import annotations

import re
from typing import Any

UNREADABLE = "[无法识别]"


class TextbookQualityError(ValueError):
    pass


def assess(text: str, *, min_chars: int = 40) -> dict[str, Any]:
    body = str(text or "")
    stripped = re.sub(r"\s+", "", body)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    seen: dict[str, int] = {}
    for line in lines:
        seen[line] = seen.get(line, 0) + 1
    duplicates = sum(count - 1 for count in seen.values() if count > 1)
    duplicate_ratio = round(duplicates / max(1, len(lines)), 3)
    unknown = body.count(UNREADABLE)
    unknown_ratio = round(unknown / max(1, len(body)), 4)
    reasons: list[str] = []
    if len(stripped) < min_chars:
        reasons.append("too_short")
    if duplicate_ratio > 0.35:
        reasons.append("duplicated")
    if unknown_ratio > 0.1:
        reasons.append("unreadable")
    return {
        "ok": not reasons,
        "chars": len(stripped),
        "lines": len(lines),
        "duplicate_ratio": duplicate_ratio,
        "unknown_ratio": unknown_ratio,
        "reasons": reasons,
    }


def ensure_quality(text: str, *, min_chars: int = 40) -> dict[str, Any]:
    report = assess(text, min_chars=min_chars)
    if not report["ok"]:
        labels = {
            "too_short": "正文过短",
            "duplicated": "重复行过多",
            "unreadable": "无法识别内容过多",
        }
        detail = "、".join(labels.get(item, item) for item in report["reasons"])
        raise TextbookQualityError(f"采集质量未通过：{detail}。请确认已进入目标章节后重试。")
    return report
