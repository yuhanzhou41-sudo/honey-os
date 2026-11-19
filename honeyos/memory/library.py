from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .repository import CognitiveMemoryRepository, MemoryNotFoundError


_HISTORY_PARTITIONS = (
    ("roleplay", "角色扮演", re.compile(r"角色扮演|虚构剧情|虚构角色|剧情分支|支线|RP\b|扮演", re.I)),
    ("fiction", "创作与世界观", re.compile(r"小说|世界观|角色设定|人物设定|剧情|创作|文风|故事设定|角色卡", re.I)),
    ("project", "项目与开发", re.compile(r"HoneyOS|项目|开发|代码|脚本|Git\b|WSL\b|部署|API\b|程序|软件|前端|后端", re.I)),
    ("study_research", "学习与研究", re.compile(r"学习|复习|考试|课程|论文|研究|实验|调研|医学|药理|统计|PPT|SCI\b", re.I)),
    ("personal", "个人与日常", re.compile(r"用户.*(?:喜欢|偏好|认为|习惯|家庭|小时候|妹妹|关系|成绩|压力|生活|个人)", re.I)),
)


def history_partition(summary: str) -> tuple[str, str]:
    text = str(summary or "")
    for key, label, pattern in _HISTORY_PARTITIONS:
        if pattern.search(text):
            return key, label
    return "other", "其他历史"


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


@dataclass(frozen=True)
class MemoryLibraryPage:
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    partitions: list[dict[str, Any]]
    sources: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "partitions": self.partitions,
            "sources": self.sources,
        }


class CognitiveMemoryLibrary:
    def __init__(self, repository: CognitiveMemoryRepository | None = None):
        self.repository = repository or CognitiveMemoryRepository()

    def list_historical(
        self,
        *,
        source_system: str | None = None,
        partition: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> MemoryLibraryPage:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        source_system = str(source_system or "").strip().lower() or None
        partition = str(partition or "").strip().lower() or None
        query = str(query or "").strip().lower() or None

        with self.repository.connect() as db:
            rows = db.execute(
                """
                SELECT
                    e.episode_id,
                    e.episode_type,
                    e.summary,
                    e.occurred_at,
                    e.captured_at,
                    e.status,
                    e.memory_origin,
                    e.source_system,
                    e.source_scope,
                    e.source_key,
                    e.confidence,
                    e.metadata_json,
                    COUNT(p.provenance_id) AS provenance_count
                FROM memory_episodes e
                LEFT JOIN memory_provenance p
                  ON p.memory_kind='episode'
                 AND p.memory_id=e.episode_id
                WHERE e.memory_origin='external'
                  AND e.status!='user_suppressed'
                GROUP BY e.episode_id
                ORDER BY COALESCE(e.occurred_at, e.captured_at) DESC, e.episode_id DESC
                """
            ).fetchall()

        filtered = []
        partition_counts: dict[str, dict[str, Any]] = {}
        source_counts: dict[str, int] = {}

        for row in rows:
            summary = str(row["summary"] or "")
            key, label = history_partition(summary)
            source = str(row["source_system"] or "unknown")
            meta = _loads(row["metadata_json"])
            partition_counts.setdefault(key, {"key": key, "label": label, "count": 0})
            partition_counts[key]["count"] += 1
            source_counts[source] = source_counts.get(source, 0) + 1

            if source_system and source.lower() != source_system:
                continue
            if partition and key != partition:
                continue
            if query and query not in summary.lower():
                continue

            filtered.append({
                "id": row["episode_id"],
                "memory_kind": "episode",
                "summary": summary,
                "occurred_at": row["occurred_at"],
                "captured_at": row["captured_at"],
                "status": row["status"],
                "origin": row["memory_origin"],
                "source_system": source,
                "source_scope": row["source_scope"],
                "source_key": row["source_key"],
                "confidence": row["confidence"],
                "partition": key,
                "partition_label": label,
                "time_start": meta.get("evidence_time_start"),
                "time_end": meta.get("evidence_time_end"),
                "raw_time": meta.get("raw_time"),
                "provenance_count": int(row["provenance_count"] or 0),
            })

        total = len(filtered)
        return MemoryLibraryPage(
            items=filtered[offset:offset + limit],
            total=total,
            limit=limit,
            offset=offset,
            partitions=sorted(partition_counts.values(), key=lambda x: (-int(x["count"]), str(x["label"]))),
            sources=[
                {"key": key, "label": "DeepSeek" if key == "deepseek" else key, "count": count}
                for key, count in sorted(source_counts.items(), key=lambda x: (-x[1], x[0]))
            ],
        )

    def get_historical(self, memory_id: str, *, include_suppressed: bool = False) -> dict[str, Any]:
        memory_id = str(memory_id or "").strip()
        with self.repository.connect() as db:
            row = db.execute(
                """
                SELECT * FROM memory_episodes
                WHERE episode_id=?
                  AND memory_origin='external'
                  AND (? OR status!='user_suppressed')
                """,
                (memory_id, 1 if include_suppressed else 0),
            ).fetchone()
            if row is None:
                raise MemoryNotFoundError(memory_id)
            provenance = db.execute(
                """
                SELECT * FROM memory_provenance
                WHERE memory_kind='episode' AND memory_id=?
                ORDER BY created_at, provenance_id
                """,
                (memory_id,),
            ).fetchall()
            revisions = db.execute(
                '''
                SELECT feedback_id,event_type,payload_json,created_at
                FROM memory_feedback_events
                WHERE memory_kind='episode'
                  AND memory_id=?
                  AND event_type IN ('user_edit','user_restore')
                ORDER BY created_at DESC, feedback_id DESC
                ''',
                (memory_id,),
            ).fetchall()
            tombstone = db.execute(
                '''
                SELECT tombstone_id,reason,created_at,lifted_at,active
                FROM memory_tombstones
                WHERE scope='memory'
                  AND memory_kind='episode'
                  AND memory_id=?
                ORDER BY created_at DESC
                LIMIT 1
                ''',
                (memory_id,),
            ).fetchone()

        meta = _loads(row["metadata_json"])
        key, label = history_partition(row["summary"])
        return {
            "id": row["episode_id"],
            "memory_kind": "episode",
            "summary": row["summary"],
            "occurred_at": row["occurred_at"],
            "captured_at": row["captured_at"],
            "status": row["status"],
            "origin": row["memory_origin"],
            "source_system": row["source_system"],
            "source_scope": row["source_scope"],
            "source_key": row["source_key"],
            "confidence": row["confidence"],
            "partition": key,
            "partition_label": label,
            "time_start": meta.get("evidence_time_start"),
            "time_end": meta.get("evidence_time_end"),
            "raw_time": meta.get("raw_time"),
            "metadata": meta,
            "revisions": [
                {
                    "id": r["feedback_id"],
                    "event_type": r["event_type"],
                    "created_at": r["created_at"],
                    "payload": _loads(r["payload_json"]),
                }
                for r in revisions
            ],
            "trash": (
                {
                    "tombstone_id": tombstone["tombstone_id"],
                    "reason": tombstone["reason"],
                    "deleted_at": tombstone["created_at"],
                    "restored_at": tombstone["lifted_at"],
                    "active": bool(tombstone["active"]),
                }
                if tombstone is not None else None
            ),
            "provenance": [
                {
                    "id": p["provenance_id"],
                    "source_system": p["source_system"],
                    "source_type": p["source_type"],
                    "source_id": p["source_id"],
                    "session_id": p["session_id"],
                    "message_id": p["message_id"],
                    "evidence_quote": p["evidence_quote"],
                    "created_at": p["created_at"],
                    "metadata": _loads(p["metadata_json"]),
                }
                for p in provenance
            ],
        }


    def update_historical(self, memory_id: str, summary: str) -> dict[str, Any]:
        current = self.get_historical(memory_id, include_suppressed=True)
        if current["origin"] != "external":
            raise ValueError("only external historical memory is editable here")
        if current["status"] == "user_suppressed":
            raise ValueError("cannot edit a memory in recycle bin")
        self.repository.update_episode_summary(memory_id, summary, actor="user")
        return self.get_historical(memory_id)

    def move_to_trash(self, memory_id: str) -> dict[str, Any]:
        current = self.get_historical(memory_id)
        if current["origin"] != "external":
            raise ValueError("only external historical memory is managed here")
        self.repository.suppress_memory(
            "episode",
            memory_id,
            reason="user_explicit_delete_to_recycle_bin",
            metadata={"surface": "memory_library"},
        )
        return self.get_historical(memory_id, include_suppressed=True)

    def restore_from_trash(self, memory_id: str) -> dict[str, Any]:
        current = self.get_historical(memory_id, include_suppressed=True)
        if current["status"] != "user_suppressed":
            raise ValueError("memory is not in recycle bin")
        self.repository.restore_memory("episode", memory_id, actor="user")
        return self.get_historical(memory_id)

    def permanently_delete_from_trash(self, memory_id: str) -> dict[str, Any]:
        current = self.get_historical(memory_id, include_suppressed=True)
        if current["origin"] != "external":
            raise ValueError("only external historical memory is managed here")
        if current["status"] != "user_suppressed":
            raise ValueError("memory must be in recycle bin before permanent delete")

        result = self.repository.permanently_delete_external_episode(
            memory_id,
            reason="user_permanent_delete",
        )
        return {
            "id": memory_id,
            "deleted": True,
            "source_system": result["source_system"],
            "reason": result["reason"],
        }

    def list_trash(self, *, limit: int = 50, offset: int = 0) -> MemoryLibraryPage:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        with self.repository.connect() as db:
            rows = db.execute(
                """
                SELECT
                    e.episode_id,e.summary,e.occurred_at,e.captured_at,e.status,
                    e.memory_origin,e.source_system,e.source_scope,e.source_key,
                    e.confidence,e.metadata_json,t.created_at AS deleted_at,
                    COUNT(p.provenance_id) AS provenance_count
                FROM memory_episodes e
                JOIN memory_tombstones t
                  ON t.scope='memory' AND t.memory_kind='episode'
                 AND t.memory_id=e.episode_id AND t.active=1
                LEFT JOIN memory_provenance p
                  ON p.memory_kind='episode' AND p.memory_id=e.episode_id
                WHERE e.memory_origin='external'
                  AND e.status='user_suppressed'
                GROUP BY e.episode_id
                ORDER BY t.created_at DESC, e.episode_id DESC
                """
            ).fetchall()

        items = []
        partition_counts: dict[str, dict[str, Any]] = {}
        source_counts: dict[str, int] = {}
        for row in rows:
            key, label = history_partition(row["summary"])
            source = str(row["source_system"] or "unknown")
            meta = _loads(row["metadata_json"])
            partition_counts.setdefault(key, {"key": key, "label": label, "count": 0})
            partition_counts[key]["count"] += 1
            source_counts[source] = source_counts.get(source, 0) + 1
            items.append({
                "id": row["episode_id"],
                "memory_kind": "episode",
                "summary": row["summary"],
                "occurred_at": row["occurred_at"],
                "captured_at": row["captured_at"],
                "status": row["status"],
                "origin": row["memory_origin"],
                "source_system": source,
                "source_scope": row["source_scope"],
                "source_key": row["source_key"],
                "confidence": row["confidence"],
                "partition": key,
                "partition_label": label,
                "time_start": meta.get("evidence_time_start"),
                "time_end": meta.get("evidence_time_end"),
                "raw_time": meta.get("raw_time"),
                "provenance_count": int(row["provenance_count"] or 0),
                "deleted_at": row["deleted_at"],
            })

        total = len(items)
        return MemoryLibraryPage(
            items=items[offset:offset + limit],
            total=total,
            limit=limit,
            offset=offset,
            partitions=sorted(partition_counts.values(), key=lambda x: (-int(x["count"]), str(x["label"]))),
            sources=[
                {"key": key, "label": "DeepSeek" if key == "deepseek" else key, "count": count}
                for key, count in sorted(source_counts.items(), key=lambda x: (-x[1], x[0]))
            ],
        )
