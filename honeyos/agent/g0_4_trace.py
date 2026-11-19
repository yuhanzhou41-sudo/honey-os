"""G0.4 metadata-only live runtime attribution.

This module must never persist prompt/context body text.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

TRACE_PATH = Path.home() / ".honeyos" / "memory" / "runtime_context_g0_4.jsonl"


def _chars(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    try:
        return len(str(value))
    except Exception:
        return 0


def _sha(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()


def _system_prompt_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value:
        return {
            "chars": 0,
            "sha256": "",
            "section_count": 0,
            "sections": [],
            "keyword_counts": {},
        }

    groups = {
        "memory": ["memory", "memories", "remember", "recall", "记忆", "记得", "回忆"],
        "retrieval": ["retrieve", "retrieval", "search memory", "memory search", "检索", "查找记忆", "搜索记忆"],
        "history": ["history", "historical", "conversation history", "历史", "聊天记录", "过去对话"],
        "provenance": ["provenance", "source system", "memory database", "来源", "数据库"],
        "identity": ["identity", "personality", "soul", "profile", "身份", "人格", "性格"],
        "relationship": ["relationship", "companion", "陪伴", "关系"],
        "style": ["style", "tone", "natural", "conversational", "语气", "风格", "自然"],
        "tools": ["tool", "tools", "function", "插件", "工具"],
    }

    def count_terms(text: str, terms: list[str]) -> int:
        low = text.lower()
        return sum(low.count(term.lower()) for term in terms)

    heading_re = re.compile(r"(?m)^(#{1,6})[ \t]+(.+?)\s*$")
    matches = list(heading_re.finditer(value))
    raw_sections = []

    if matches:
        if matches[0].start() > 0:
            raw_sections.append(value[:matches[0].start()])
        for idx, match in enumerate(matches):
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(value)
            raw_sections.append(value[match.start():end])
    else:
        raw_sections = [value]

    sections = []
    for idx, raw in enumerate(raw_sections, 1):
        sections.append(
            {
                "index": idx,
                "chars": len(raw),
                "sha256": _sha(raw),
                "category_counts": {
                    group: count_terms(raw, terms)
                    for group, terms in groups.items()
                },
            }
        )

    return {
        "chars": len(value),
        "sha256": _sha(value),
        "section_count": len(sections),
        "sections": sections,
        "keyword_counts": {
            group: count_terms(value, terms)
            for group, terms in groups.items()
        },
    }


def write_g0_4_runtime_trace(
    *,
    session_id: str | None,
    turn_id: str | None,
    system_prompt: Any,
    plugin_final_context: Any,
    plugin_hook_context: Any,
    runtime_time_context: Any,
    gateway_notes_context: Any,
    path: Path | None = None,
) -> None:
    """Append one metadata-only G0.4 row. Always fail open."""
    try:
        target = path or TRACE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)

        row = {
            "phase": "G0.4",
            "mode": "metadata_only_live_runtime_attribution",
            "session_id": str(session_id or ""),
            "turn_id": str(turn_id or ""),
            "system_prompt": _system_prompt_metadata(system_prompt),
            "plugin_sidecar": {
                "final_chars": _chars(plugin_final_context),
                "pre_llm_hook_chars": _chars(plugin_hook_context),
                "runtime_time_context_chars": _chars(runtime_time_context),
                "gateway_notes_chars": _chars(gateway_notes_context),
            },
        }

        with target.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        return
