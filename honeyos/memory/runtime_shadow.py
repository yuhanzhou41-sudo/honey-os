from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .library import history_partition
from .repository import CognitiveMemoryRepository

logger = logging.getLogger(__name__)

_AUDIT_LOCK = threading.Lock()
_LATIN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u3400-\u9fff]{2,}")

_LATIN_STOP = {
    "the", "and", "for", "with", "that", "this", "what", "when", "where",
    "have", "has", "had", "was", "were", "are", "you", "your", "about",
    "from", "into", "can", "could", "would", "should", "please",
}
_CJK_STOP = {
    "什么", "怎么", "这个", "那个", "之前", "现在", "可以", "一下", "一个",
    "我们", "你们", "他们", "自己", "是不是", "有没有", "相关", "里面",
    "时候", "还是", "已经", "然后", "因为", "所以", "如果", "但是",
    "系统", "的系统", "关系", "家庭",
}

_ROLEPLAY_HINTS = (
    "角色扮演", "扮演", "rp", "rpg", "跑团", "角色卡", "代入", "oc",
)
_FICTION_HINTS = (
    "小说", "剧情", "世界观", "设定", "故事", "人物", "角色", "写作",
    "创作", "同人",
)


_QUERY_SCAFFOLD_PHRASES = (
    "我以前有没有谈到过", "以前有没有谈到过", "我以前谈到过",
    "找一下我以前", "找找我以前", "找一下以前", "找找以前",
    "找一下", "找找", "我以前", "以前",
    "角色扮演里的", "角色扮演里", "角色扮演中的", "角色扮演中",
    "角色扮演", "有关的", "相关的", "有关", "相关",
    "目前开发到哪个阶段了", "目前开发到哪个阶段",
    "开发到哪个阶段了", "开发到哪个阶段",
    "现在做到哪里了", "之前做到哪里了",
    "剧情", "故事", "如何", "吗",
)

_RUNTIME_ROLEPLAY_RE = re.compile(
    r"角色扮演|虚构角色|剧情分支|支线|\bRP\b|扮演",
    re.I,
)
_RUNTIME_FICTION_RE = re.compile(
    r"虚构|小说|世界观|角色设定|人物设定|故事设定|世界书|角色卡|"
    r"架空|作品|创作|同人|备选线|备选结局|轮回故事|剧情|"
    r"在《[^》]+》中|角色JSON|用户为.{0,24}(?:设定|设计|创作)",
    re.I,
)


def _query_for_terms(query: str) -> str:
    q = _normalize(query)
    for phrase in _QUERY_SCAFFOLD_PHRASES:
        q = q.replace(phrase.lower(), " ")
    return " ".join(q.split())


def _runtime_memory_namespace(summary: str, presentation_partition: str) -> str:
    text = str(summary or "")
    if _RUNTIME_ROLEPLAY_RE.search(text):
        return "roleplay"
    if _RUNTIME_FICTION_RE.search(text):
        return "fiction"
    if presentation_partition in {"roleplay", "fiction"}:
        return presentation_partition
    return "general"

@dataclass(frozen=True)
class ShadowCandidate:
    id: str
    source_system: str
    source_key: str
    partition: str
    score: float
    reason: str
    selected: bool
    char_cost: int
    summary_preview: str


@dataclass(frozen=True)
class ShadowRetrievalResult:
    query: str
    namespace: str
    selected: tuple[ShadowCandidate, ...]
    rejected: tuple[ShadowCandidate, ...]
    total_char_cost: int
    prompt_injection: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "namespace": self.namespace,
            "selected": [asdict(item) for item in self.selected],
            "rejected": [asdict(item) for item in self.rejected],
            "total_char_cost": self.total_char_cost,
            "prompt_injection": self.prompt_injection,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _query_namespace(query: str) -> str:
    q = _normalize(query)
    if any(hint in q for hint in _ROLEPLAY_HINTS):
        return "roleplay"
    if any(hint in q for hint in _FICTION_HINTS):
        return "fiction"
    return "general"


def _query_terms(query: str) -> list[tuple[str, float]]:
    q = _query_for_terms(query)
    weighted: dict[str, float] = {}

    for token in _LATIN_RE.findall(q):
        token = token.lower()
        if len(token) < 3 or token in _LATIN_STOP:
            continue
        weighted[token] = max(weighted.get(token, 0.0), min(4.0, 1.5 + len(token) / 4.0))

    for run in _CJK_RE.findall(q):
        if len(run) <= 4 and run not in _CJK_STOP:
            # Whole cleaned short subjects are intentional signal.
            # Keep incidental 2-char n-grams weak below, but let an explicit
            # subject such as "骑士" clear the 3.0 selection threshold.
            whole_weight = 3.0 if len(run) == 2 else float(len(run))
            weighted[run] = max(weighted.get(run, 0.0), whole_weight)
        # 2-4 character ngrams give deterministic Chinese lexical recall
        # without adding a tokenizer dependency.
        for n in (4, 3, 2):
            if len(run) < n:
                continue
            for i in range(0, len(run) - n + 1):
                gram = run[i:i+n]
                if gram in _CJK_STOP:
                    continue
                gram_weight = 1.0 if n == 2 else float(n)
                weighted[gram] = max(weighted.get(gram, 0.0), gram_weight)

    # Keep the most informative terms so long turns cannot make the scan noisy.
    ranked = sorted(weighted.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return ranked[:24]


def _score(summary: str, terms: list[tuple[str, float]]) -> tuple[float, list[str]]:
    text = _normalize(summary)
    score = 0.0
    hits: list[str] = []
    for term, weight in terms:
        count = text.count(term)
        if count:
            hits.append(term)
            score += weight * min(count, 3)
    # Require more than one weak 2-char coincidence, or one stronger token.
    return score, hits


def _namespace_allows(query_namespace: str, partition: str) -> bool:
    if partition == "roleplay":
        return query_namespace in {"roleplay", "fiction"}
    if partition == "fiction":
        return query_namespace in {"fiction", "roleplay"}
    return True


class CognitiveMemoryShadowRetriever:
    """Read-only lexical shadow retriever for Phase F1.

    It never produces prompt text and never mutates Cognitive Memory.
    """

    def __init__(
        self,
        repository: CognitiveMemoryRepository | None = None,
        *,
        audit_path: Path | str | None = None,
        max_results: int = 3,
        char_budget: int = 900,
        max_preview_per_item: int = 450,
    ) -> None:
        self.repository = repository or CognitiveMemoryRepository()
        self.max_results = max(1, int(max_results))
        self.char_budget = max(1, int(char_budget))
        self.max_preview_per_item = max(1, int(max_preview_per_item))
        self.audit_path = (
            Path(audit_path).expanduser()
            if audit_path is not None
            else self.repository.memory_dir / "runtime_shadow.jsonl"
        )

    def retrieve(
        self,
        query: str,
        *,
        session_id: str = "",
        turn_id: str = "",
        write_audit: bool = True,
    ) -> ShadowRetrievalResult:
        clean_query = str(query or "").strip()
        namespace = _query_namespace(clean_query)
        terms = _query_terms(clean_query)
        if not clean_query or not terms:
            result = ShadowRetrievalResult(
                query=clean_query,
                namespace=namespace,
                selected=(),
                rejected=(),
                total_char_cost=0,
            )
            if write_audit:
                self._write_audit(result, session_id=session_id, turn_id=turn_id)
            return result

        rows: list[Any]
        with self.repository.connect() as db:
            rows = db.execute(
                """
                SELECT
                    e.episode_id,e.summary,e.source_system,e.source_key,
                    e.occurred_at,e.captured_at,e.metadata_json
                FROM memory_episodes e
                WHERE e.memory_origin='external'
                  AND e.status='active'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM memory_tombstones t
                      WHERE t.active=1
                        AND t.scope='source'
                        AND t.source_system=e.source_system
                        AND t.source_id=e.source_key
                  )
                ORDER BY COALESCE(e.occurred_at,e.captured_at) DESC, e.episode_id
                """
            ).fetchall()

        scored: list[tuple[float, Any, str, list[str]]] = []
        rejected: list[ShadowCandidate] = []

        for row in rows:
            summary = str(row["summary"] or "")
            partition, _partition_label = history_partition(summary)
            runtime_namespace = _runtime_memory_namespace(summary, partition)
            score, hits = _score(summary, terms)

            # Phase F1 uses two thresholds:
            # - audit threshold (2.0): weak but meaningful lexical overlap can be
            #   recorded when a namespace gate rejects it;
            # - selection threshold (3.0): only stronger matches may be selected.
            if score < 2.0:
                continue

            if not _namespace_allows(namespace, runtime_namespace):
                rejected.append(
                    ShadowCandidate(
                        id=str(row["episode_id"]),
                        source_system=str(row["source_system"] or ""),
                        source_key=str(row["source_key"] or ""),
                        partition=partition,
                        score=round(score, 3),
                        reason="namespace_mismatch",
                        selected=False,
                        char_cost=0,
                        summary_preview=summary[:160],
                    )
                )
                continue

            if score < 3.0:
                continue

            reason = "lexical:" + ",".join(hits[:8])
            scored.append((score, row, partition, hits))

        scored.sort(
            key=lambda item: (
                -item[0],
                str(item[1]["occurred_at"] or item[1]["captured_at"] or ""),
                str(item[1]["episode_id"]),
            )
        )

        selected: list[ShadowCandidate] = []
        total = 0
        for score, row, partition, hits in scored:
            summary = str(row["summary"] or "")
            if len(selected) >= self.max_results:
                rejected.append(
                    ShadowCandidate(
                        id=str(row["episode_id"]),
                        source_system=str(row["source_system"] or ""),
                        source_key=str(row["source_key"] or ""),
                        partition=partition,
                        score=round(score, 3),
                        reason="result_limit",
                        selected=False,
                        char_cost=0,
                        summary_preview=summary[:160],
                    )
                )
                continue

            remaining = self.char_budget - total
            if remaining <= 0:
                rejected.append(
                    ShadowCandidate(
                        id=str(row["episode_id"]),
                        source_system=str(row["source_system"] or ""),
                        source_key=str(row["source_key"] or ""),
                        partition=partition,
                        score=round(score, 3),
                        reason="char_budget",
                        selected=False,
                        char_cost=0,
                        summary_preview=summary[:160],
                    )
                )
                continue

            preview = summary[: min(self.max_preview_per_item, remaining)]
            cost = len(preview)
            selected.append(
                ShadowCandidate(
                    id=str(row["episode_id"]),
                    source_system=str(row["source_system"] or ""),
                    source_key=str(row["source_key"] or ""),
                    partition=partition,
                    score=round(score, 3),
                    reason="lexical:" + ",".join(hits[:8]),
                    selected=True,
                    char_cost=cost,
                    summary_preview=preview,
                )
            )
            total += cost

        # Audit only the strongest rejected candidates to keep logs bounded.
        rejected.sort(key=lambda item: (-item.score, item.id))
        result = ShadowRetrievalResult(
            query=clean_query,
            namespace=namespace,
            selected=tuple(selected),
            rejected=tuple(rejected[:12]),
            total_char_cost=total,
        )
        if write_audit:
            self._write_audit(result, session_id=session_id, turn_id=turn_id)
        return result

    def _write_audit(
        self,
        result: ShadowRetrievalResult,
        *,
        session_id: str,
        turn_id: str,
    ) -> None:
        payload = {
            "timestamp": _now(),
            "mode": "shadow",
            "session_id": str(session_id or ""),
            "turn_id": str(turn_id or ""),
            **result.to_dict(),
        }
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            with _AUDIT_LOCK:
                with self.audit_path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        except Exception:
            logger.debug("Cognitive Memory shadow audit write failed", exc_info=True)


def run_cognitive_memory_shadow(
    query: str,
    *,
    session_id: str = "",
    turn_id: str = "",
) -> ShadowRetrievalResult:
    """Fail-open Phase F1 entry point used by the turn prologue."""
    return CognitiveMemoryShadowRetriever().retrieve(
        query,
        session_id=session_id,
        turn_id=turn_id,
        write_audit=True,
    )
