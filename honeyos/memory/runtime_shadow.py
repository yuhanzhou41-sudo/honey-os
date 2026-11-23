from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
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

# A small set of precise equivalences. Broad labels such as “red” or “rain”
# alone would overlap too many unrelated memories.
_SENSORY_ALIASES = (
    ("color:navy", "藏青色", "海军蓝", "navy blue"),
    ("color:lavender", "淡紫色", "薰衣草紫", "lavender purple"),
    ("smell:petrichor", "雨后泥土味", "雨后土腥味", "潮湿泥土的气味", "petrichor"),
    ("smell:osmanthus", "桂花香", "桂花的香味", "osmanthus scent"),
    ("sound:cicadas", "蝉鸣", "知了叫", "cicadas chirping"),
    ("sound:wind-chimes", "风铃声", "风铃响", "wind chimes"),
)

_BROAD_RECALL = re.compile(
    r"(?:回顾|回忆|找出|列出|整理|梳理|汇总|查找).{0,35}(?:往事|经历|记忆|聊天历史|聊天记录)"
    r"|(?:所有|全部|完整).{0,20}(?:经历|记忆|聊天记录)"
    r"|\b(?:recall|list|review|find)\b.{0,45}\b(?:memories|past conversations)\b",
    re.IGNORECASE,
)
EXPANDED_RECALL_ITEMS = 64
EXPANDED_RECALL_CHARS = 8_000
_DATED_RECALL = re.compile(r"(?<![0-9])(\d{4})[-年](\d{1,2})[-月](\d{1,2})(?:日)?(?![0-9])")


def requests_broad_recall(query: str) -> bool:
    return bool(_BROAD_RECALL.search(query))


def _recall_dates(query: str) -> tuple[date, date] | None:
    matches = list(_DATED_RECALL.finditer(query))
    if len(matches) not in (1, 2):
        return None
    if len(matches) == 2 and query[matches[0].end():matches[1].start()].strip() not in {"到", "至", "—", "~", "～", "to"}:
        return None
    try:
        days = [date(*(int(part) for part in match.groups())) for match in matches]
    except ValueError:
        return None
    return (days[0], days[-1]) if days[0] <= days[-1] else None


def _recall_strength(row: Any, now: datetime) -> float:
    try:
        happened = datetime.fromisoformat(row["occurred_at"] or row["captured_at"] or "")
    except ValueError:
        return 1.0
    if happened.tzinfo is None:
        return 1.0
    age_days = max(0.0, (now - happened).total_seconds() / 86400)
    importance = max(float(row[key] or 0) for key in ("recall_affinity", "user_emphasis", "unresolvedness"))
    half_life_days = 90 + 270 * max(0.0, min(1.0, importance))
    return 2 ** (-age_days / half_life_days)


def _sensory_cues(text: str) -> set[str]:
    normalized = _normalize(text)
    return {cue for cue, *aliases in _SENSORY_ALIASES
            if any(alias in normalized for alias in aliases)}


def _rank_adjustment(row: Any, now: datetime) -> float:
    # Salience is optional for existing memories. Its values only rerank
    # candidates already admitted by topic or a precise sensory cue.
    def unit(field: str) -> float:
        return max(0.0, min(1.0, float(row[field] or 0)))

    recency = 0.0
    if row["occurred_at"]:
        try:
            happened = datetime.fromisoformat(row["occurred_at"])
            if happened.tzinfo is not None:
                days = max(0.0, (now - happened).total_seconds() / 86400)
                recency = 0.5 * (2 ** (-days / 30))
        except ValueError:
            pass
    return (
        recency + 0.4 * unit("personal_relevance") + 0.6 * unit("user_emphasis")
        + 0.25 * unit("arousal") + 0.25 * unit("unresolvedness")
        - unit("mention_sensitivity")
    )

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
    explicit_recall: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "namespace": self.namespace,
            "selected": [asdict(item) for item in self.selected],
            "rejected": [asdict(item) for item in self.rejected],
            "total_char_cost": self.total_char_cost,
            "prompt_injection": self.prompt_injection,
            "explicit_recall": self.explicit_recall,
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
    """Read-only lexical and sensory retriever.

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
        adaptive: bool = False,
        now: datetime | None = None,
    ) -> ShadowRetrievalResult:
        clean_query = str(query or "").strip()
        namespace = _query_namespace(clean_query)
        explicit_recall = False
        if adaptive:
            from honeyos.routing.rules import route_by_rules

            route = route_by_rules(clean_query)
            explicit_recall = requests_broad_recall(clean_query) or (route is not None and route.intent == "recall")
        date_scope = _recall_dates(clean_query) if explicit_recall else None
        subject = clean_query
        if date_scope:
            subject = _DATED_RECALL.sub(" ", subject)
            subject = re.sub(
                r"回顾|回忆|找出|查找|聊天历史|聊天记录|记录|所有|全部|经历|记忆|"
                r"\b(?:review|recall|list|find|all|memories|past conversations)\b",
                " ", subject, flags=re.I,
            )
        terms = _query_terms(subject)
        cues = _sensory_cues(clean_query)
        if not terms and not cues and not date_scope:
            result = ShadowRetrievalResult(
                query=clean_query,
                namespace=namespace,
                selected=(),
                rejected=(),
                total_char_cost=0,
                explicit_recall=explicit_recall,
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
                    e.occurred_at,e.captured_at,
                    s.personal_relevance,s.user_emphasis,s.arousal,
                    s.unresolvedness,s.mention_sensitivity,s.recall_affinity
                FROM memory_episodes e
                LEFT JOIN memory_salience s
                    ON s.memory_kind='episode' AND s.memory_id=e.episode_id
                WHERE e.memory_origin='external'
                  AND (e.status='active' OR (? AND e.status='dormant'))
                  AND NOT EXISTS (
                      SELECT 1
                      FROM memory_tombstones t
                      WHERE t.active=1
                        AND t.scope='source'
                        AND (
                            (t.source_system=e.source_system AND t.source_id=e.source_key)
                            OR EXISTS (
                                SELECT 1 FROM memory_provenance p
                                WHERE p.memory_kind='episode' AND p.memory_id=e.episode_id
                                  AND p.source_system=t.source_system AND p.source_id=t.source_id
                            )
                        )
                  )
                ORDER BY COALESCE(e.occurred_at,e.captured_at) DESC, e.episode_id
                """, (explicit_recall,)
            ).fetchall()

        scored: list[tuple[float, Any, str, str]] = []
        rejected: list[ShadowCandidate] = []
        now = now or datetime.now(timezone.utc)
        # S4.5 / Task D: external history (DeepSeek import) is user-owned
        # material, not a native Honey episode. It must be retrieved by pure
        # topical relevance only. Honey's *current* simulated physiology
        # (epinephrine) is deliberately NOT used to weight it.
        attention = 0.0

        for row in rows:
            if date_scope:
                # Import date is not the date of the original conversation.
                try:
                    happened = datetime.fromisoformat(row["occurred_at"] or "").date()
                except ValueError:
                    continue
                if not date_scope[0] <= happened <= date_scope[1]:
                    continue
            summary = str(row["summary"] or "")
            partition, _partition_label = history_partition(summary)
            runtime_namespace = _runtime_memory_namespace(summary, partition)
            score, hits = _score(summary, terms)
            shared_cues = sorted(cues & _sensory_cues(summary)) if cues else []
            if shared_cues or (date_scope and not terms):
                score = max(score, 3.0)

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

            strength = _recall_strength(row, now) if adaptive else 1.0
            threshold = 3.0 + (0.0 if explicit_recall else 3.0 * max(0.0, 0.65 - strength))
            if score < threshold:
                continue

            reason = "lexical:" + ",".join(hits[:8])
            if date_scope:
                reason += "|date_scope"
            if shared_cues:
                reason += "|sensory:" + ",".join(shared_cues)
            state_boost = attention * max(0.0, min(1.0, float(row["arousal"] or 0)))
            scored.append((score + _rank_adjustment(row, now) + state_boost, row, partition, reason))

        scored.sort(
            key=lambda item: (
                -item[0],
                str(item[1]["occurred_at"] or item[1]["captured_at"] or ""),
                str(item[1]["episode_id"]),
            )
        )

        selected: list[ShadowCandidate] = []
        included_summaries: set[str] = set()
        total = 0
        for score, row, partition, reason in scored:
            summary = str(row["summary"] or "")
            normalized_summary = _normalize(summary)
            if normalized_summary in included_summaries:
                continue
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
                    reason=reason,
                    selected=True,
                    char_cost=cost,
                    summary_preview=preview,
                )
            )
            included_summaries.add(normalized_summary)
            total += cost

        # Expand only from the strongest directly retrieved episode. Reusing
        # the filtered rows also enforces source tombstones on the other end.
        if adaptive and not explicit_recall and selected and len(selected) < self.max_results:
            anchor = selected[0]
            eligible_rows = {str(row["episode_id"]): row for row in rows}
            with self.repository.connect() as db:
                neighbors = db.execute(
                    """
                    SELECT q.memory_id, COUNT(DISTINCT p.message_id) AS shared
                    FROM memory_provenance p JOIN memory_provenance q
                      ON q.source_system=p.source_system AND q.source_id=p.source_id
                     AND q.session_id IS p.session_id AND q.message_id=p.message_id
                    WHERE p.memory_kind='episode' AND q.memory_kind='episode'
                      AND p.memory_id=? AND q.memory_id<>p.memory_id
                      AND p.message_id IS NOT NULL AND p.message_id<>''
                    GROUP BY q.memory_id ORDER BY shared DESC, q.memory_id
                    """,
                    (anchor.id,),
                ).fetchall()
            used_ids = {item.id for item in selected}
            anchor_namespace = _runtime_memory_namespace(
                eligible_rows[anchor.id]["summary"], anchor.partition
            )
            for neighbor in neighbors:
                item_id = neighbor["memory_id"]
                row = eligible_rows.get(item_id)
                if row is None or item_id in used_ids or _recall_strength(row, now) < 0.45:
                    continue
                summary = str(row["summary"] or "")
                partition, _ = history_partition(summary)
                if (
                    _runtime_memory_namespace(summary, partition) != anchor_namespace
                    or _normalize(summary) in included_summaries
                ):
                    continue
                preview = summary[: min(self.max_preview_per_item, self.char_budget - total)]
                if preview:
                    selected.append(ShadowCandidate(
                        id=item_id, source_system=str(row["source_system"] or ""),
                        source_key=str(row["source_key"] or ""), partition=partition,
                        score=0.0, reason="shared_source_message", selected=True,
                        char_cost=len(preview), summary_preview=preview,
                    ))
                    total += len(preview)
                break

        # Audit only the strongest rejected candidates to keep logs bounded.
        rejected.sort(key=lambda item: (-item.score, item.id))
        result = ShadowRetrievalResult(
            query=clean_query,
            namespace=namespace,
            selected=tuple(selected),
            rejected=tuple(rejected[:12]),
            total_char_cost=total,
            explicit_recall=explicit_recall,
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
    expanded: bool = False,
    adaptive: bool = False,
) -> ShadowRetrievalResult:
    """Fail-open Phase F1 entry point used by the turn prologue."""
    if adaptive:
        try:
            from honeyos.study.memory_salience import sync_active_study_memory_salience

            sync_active_study_memory_salience()
        except Exception:
            logger.debug("Study memory salience synchronization failed", exc_info=True)
    retriever = (
        CognitiveMemoryShadowRetriever(max_results=EXPANDED_RECALL_ITEMS, char_budget=EXPANDED_RECALL_CHARS)
        if expanded else CognitiveMemoryShadowRetriever()
    )
    return retriever.retrieve(
        query,
        session_id=session_id,
        turn_id=turn_id,
        write_audit=True,
        adaptive=adaptive,
    )
