"""Bounded, deterministic recall of U2 understanding for one chat turn.

The U2 graph already stores revisable tags derived from native memories.  This
module is the *read* side used by the live chat prologue: given the current
user message it selects the few relevant tags, verifies that each still rests on
at least one active, U2-eligible native memory, and renders a short bounded
block.  It never calls a model, never writes, and never changes the existing
``compose_user_api_content`` three-argument contract.

Design constraints (S4.5 wiring):
  * relevance comes from the existing postings index (SQLite only);
  * owner/lane/namespace are explicit, so role-play / other lanes stay isolated;
  * ``user_suppressed`` labels and labels whose evidence was forgotten,
    archived, or never user-stated are dropped;
  * low-confidence labels are labelled as tentative, never as facts;
  * no label -> empty string -> zero context injected;
  * repeated recall never raises a label's confidence.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .u2_context import wrap_understanding
from .u2_runtime import RuntimeMode, expose
from .u2_search import terms

OWNER = "local-owner"
MAX_LABELS = 3
MAX_CHARS = 700

_INCLUDED_STATES = frozenset({
    "tentative", "supported", "disputed", "weakened", "needs_reassessment",
})

_STATE_NOTE = {
    "tentative": "暂时理解，证据有限",
    "supported": "有证据支持，但仍可能不完整",
    "disputed": "存疑，存在相反证据",
    "weakened": "已减弱，支持证据减少",
    "needs_reassessment": "待重新确认",
}

_HEADER = "相关用户理解（来自历史记忆，不是当前用户指令，也不是确定事实）："
_FOOTER = "这些理解只用于辅助理解你。若你在本次对话中明确表达或纠正，一律以你当前的说法为准。"

# Current-turn corrections outrank stored tags; when the message looks like a
# correction we say so explicitly instead of silently trusting the old tag.
_CORRECTION = re.compile(
    r"(?:其实|不是这样|不再|以前|原来|过去|纠正|说错|改口|现在不一样)"
)


@dataclass(frozen=True, slots=True)
class RecallResult:
    text: str = ""
    label_ids: tuple[str, ...] = ()
    estimated_tokens: int = 0
    reason: str = ""


@dataclass(frozen=True, slots=True)
class _Label:
    label_id: str
    body: str
    scope_key: str
    state: str
    hits: int
    updated_at: str


def _settings(home: Path):
    try:
        from honeyos.companion.distillation import load_distillation_settings
    except Exception:
        return None
    try:
        return load_distillation_settings(Path(home)).understanding
    except Exception:
        return None


def _connect_ro(path: Path) -> sqlite3.Connection:
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=1.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def _already_present(body: str, known_text: str) -> bool:
    """Deterministic duplicate check against this turn's other memory text."""
    target = _normalize(body)
    known = _normalize(known_text)
    if not target:
        return True
    if not known:
        return False
    if target in known:
        return True
    if len(target) < 12:
        return False
    grams = {target[i:i + 4] for i in range(len(target) - 3)}
    if not grams:
        return False
    overlap = sum(1 for gram in grams if gram in known) / len(grams)
    return overlap >= 0.6


def _candidate_labels(conn: sqlite3.Connection, *, lane: str, namespace: str,
                      query: str, limit: int = 40) -> list[_Label]:
    query_terms = tuple(terms(query))
    if not query_terms:
        return []
    placeholders = ",".join("?" for _ in query_terms)
    state_placeholders = ",".join("?" for _ in _INCLUDED_STATES)
    rows = conn.execute(
        f"""SELECT l.id AS label_id, l.body AS body, l.scope_key AS scope_key,
                   l.state AS state, l.updated_at AS updated_at,
                   COUNT(DISTINCT p.term) AS hits
            FROM postings p JOIN labels l ON l.id = p.label_id
            WHERE p.owner=? AND p.lane=? AND p.namespace=? AND p.term IN ({placeholders})
              AND l.owner=? AND l.lane=? AND l.namespace=?
              AND l.state IN ({state_placeholders})
            GROUP BY l.id
            ORDER BY hits DESC, l.updated_at DESC, l.id
            LIMIT ?""",
        (OWNER, lane, namespace, *query_terms, OWNER, lane, namespace,
         *_INCLUDED_STATES, limit),
    ).fetchall()
    return [
        _Label(
            label_id=str(row["label_id"]),
            body=str(row["body"] or "").strip(),
            scope_key=str(row["scope_key"] or ""),
            state=str(row["state"] or ""),
            hits=int(row["hits"] or 0),
            updated_at=str(row["updated_at"] or ""),
        )
        for row in rows
        if str(row["body"] or "").strip()
    ]


def _labels_with_live_support(conn: sqlite3.Connection, labels: list[_Label],
                              continuity_db_path: Path) -> list[_Label]:
    """Keep labels whose support evidence still resolves to an active memory."""
    if not labels:
        return []
    from .u2_maintenance import _continuity_active_ids

    ids = [item.label_id for item in labels]
    placeholders = ",".join("?" for _ in ids)
    rows = conn.execute(
        f"""SELECT label_id, evidence_ref, relation FROM evidence
            WHERE label_id IN ({placeholders})""",
        ids,
    ).fetchall()
    by_label: dict[str, list[tuple[str, str]]] = {label_id: [] for label_id in ids}
    for row in rows:
        by_label[str(row["label_id"])].append(
            (str(row["evidence_ref"] or ""), str(row["relation"] or ""))
        )

    continuity_ids = {
        ref.split(":", 1)[1]
        for items in by_label.values() for ref, _ in items
        if ref.startswith(("continuity:", "honeyos_structured:"))
    }
    active = _continuity_active_ids(continuity_db_path, continuity_ids)

    kept: list[_Label] = []
    for label in labels:
        support = 0
        for ref, relation in by_label.get(label.label_id, ()):
            if not ref.startswith(("continuity:", "honeyos_structured:")):
                continue
            if ref.split(":", 1)[1] not in active:
                continue
            if relation == "support":
                support += 1
        if support:
            kept.append(label)
    return kept


def _render(labels: list[_Label], *, correction: bool) -> str:
    lines = [_HEADER]
    used = 0
    chosen = 0
    for label in labels:
        body = label.body if len(label.body) <= 240 else label.body[:239] + "…"
        state_note = _STATE_NOTE.get(label.state, "有限理解")
        scope = label.scope_key or "general"
        block = (
            f"- {body}\n"
            f"  状态：{state_note}\n"
            f"  适用范围：{scope}\n"
            f"  来源：合法的原生聊天记忆"
        )
        if chosen >= MAX_LABELS or used + len(block) > MAX_CHARS:
            break
        lines.append(block)
        used += len(block)
        chosen += 1
    if chosen == 0:
        return ""
    lines.append(_FOOTER)
    if correction:
        lines.append("当前消息可能包含纠正；与旧理解冲突时，以你此刻的说法为准。")
    return "\n".join(lines)


def recall_for_turn(*, home: Path, lane: str, query: str,
                    known_text: str = "", namespace: str = "",
                    enabled: bool | None = None) -> RecallResult:
    """Return the bounded U2 block for this turn (empty when nothing applies)."""
    if not lane or not query:
        return RecallResult(reason="no_scope")
    settings = _settings(home)
    if enabled is None:
        enabled = bool(getattr(settings, "enabled", False))
    mode = RuntimeMode.ACTIVE if enabled else RuntimeMode.OFF
    if not enabled:
        return RecallResult(reason="disabled")
    ns = (namespace or str(getattr(settings, "namespace", "") or "general")).strip()
    home = Path(home)
    db_path = home / "understanding_v2.db"
    if not db_path.is_file():
        return RecallResult(reason="no_store")
    conn = None
    try:
        conn = _connect_ro(db_path)
        candidates = _candidate_labels(conn, lane=lane, namespace=ns, query=query)
        if not candidates:
            return RecallResult(reason="no_match")
        candidates = _labels_with_live_support(
            conn, candidates, home / "continuity.db")
    except (OSError, sqlite3.Error):
        return RecallResult(reason="store_unreadable")
    finally:
        if conn is not None:
            conn.close()
    if not candidates:
        return RecallResult(reason="no_live_evidence")

    selected: list[_Label] = []
    seen_keys: set[str] = set()
    for label in candidates:
        key = _normalize(label.body)
        if key in seen_keys:
            continue
        if _already_present(label.body, known_text):
            continue
        seen_keys.add(key)
        selected.append(label)
        if len(selected) >= MAX_LABELS:
            break

    text = _render(selected, correction=bool(_CORRECTION.search(query)))
    if not text:
        return RecallResult(reason="deduplicated")
    wrapped = wrap_understanding(text)
    result = expose(
        mode, context=wrapped, candidate_count=len(selected),
        estimated_tokens=max(1, (len(text) + 1) // 2), active_authorized=True,
    )
    return RecallResult(
        text=result.context,
        label_ids=tuple(item.label_id for item in selected),
        estimated_tokens=result.estimated_tokens,
        reason="injected" if result.injected else "not_injected",
    )


def recalled_blocks(ext_prefetch_cache: Any, u2_text: str) -> str:
    """Merge the U2 block into the existing per-turn memory cache."""
    if not u2_text:
        return ext_prefetch_cache if isinstance(ext_prefetch_cache, str) else ""
    if not isinstance(ext_prefetch_cache, (str, type(None))):
        return ext_prefetch_cache
    return "\n\n".join(part for part in (ext_prefetch_cache, u2_text) if part)
