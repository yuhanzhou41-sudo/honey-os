"""Metadata-only runtime context contribution trace for G0 audit.

Never writes prompt, user, memory, plugin, or history body text.
Only counts, booleans, namespaces, and SHA-256 digests are persisted.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from honeyos.core.constants import get_honeyos_home


def context_trace_enabled() -> bool:
    return os.environ.get("HONEYOS_CONTEXT_TRACE") == "1"


def append_context_trace(filename: str, row: dict[str, Any], path: Path | None) -> None:
    target = path if path is not None else get_honeyos_home() / "memory" / filename
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(target, flags, 0o600), "a", encoding="utf-8") as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")



def _chars(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    try:
        return len(str(value))
    except Exception:
        return 0


def _sha256_text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()


def _history_stats(messages: Any) -> dict[str, Any]:
    if not isinstance(messages, list):
        return {"messages": 0, "role_counts": {}, "content_chars": 0}

    role_counts: dict[str, int] = {}
    content_chars = 0
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("system", "developer", "user", "assistant", "tool", "function"):
            role = "unknown"
        role_counts[role] = role_counts.get(role, 0) + 1
        content_chars += _chars(msg.get("content"))

    return {
        "messages": len(messages),
        "role_counts": role_counts,
        "content_chars": content_chars,
    }


def write_context_source_trace(
    *,
    session_id: str | None,
    turn_id: str | None,
    query_namespace: str | None,
    system_prompt: Any,
    history_messages: Any,
    clean_user_message: Any,
    native_memory_context: Any,
    cognitive_context: Any,
    cognitive_item_count: int | None,
    plugin_user_context: Any,
    final_memory_context: Any,
    api_content: Any,
    path: Path | None = None,
) -> None:
    """Append one metadata-only row. Any trace failure is fail-open."""
    if path is None and not context_trace_enabled():
        return
    try:
        clean_chars = _chars(clean_user_message)
        api_chars = _chars(api_content)
        row = {
            "phase": "G0.3",
            "mode": "metadata_only_runtime_context_trace",
            "session_sha256": _sha256_text(session_id),
            "turn_sha256": _sha256_text(turn_id),
            "query_namespace": query_namespace if query_namespace in ("general", "roleplay", "fiction") else "",
            "system_prompt": {
                "chars": _chars(system_prompt),
                "sha256": _sha256_text(system_prompt),
            },
            "history": _history_stats(history_messages),
            "current_turn": {
                "clean_user_chars": clean_chars,
                "native_memory_chars": _chars(native_memory_context),
                "cognitive_memory_chars": _chars(cognitive_context),
                "cognitive_item_count": int(cognitive_item_count or 0),
                "plugin_context_chars": _chars(plugin_user_context),
                "final_memory_context_chars": _chars(final_memory_context),
                "api_content_chars": api_chars,
                "api_extra_chars": max(0, api_chars - clean_chars),
            },
        }

        append_context_trace("runtime_context_sources.jsonl", row, path)
    except Exception:
        return
