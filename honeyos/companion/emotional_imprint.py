"""Historical emotional imprint for structured long-term memories.

After :mod:`distillation` saves background items into ``continuity.db``,
this module attaches a bounded "emotional imprint" describing what Honey's
own observable state was at the time the memory was formed.

Design scope (S4 freeze):

* **Only** native items produced by the MemoryDistiller — ``episode``
  ("共同经历", long-term, no expiry), ``commitment`` ("答应过的"),
  ``open_loop`` ("待续") — qualify.  We deliberately exclude
  ``temporary_state`` because it describes the user's transient state
  rather than an event Honey herself experienced, and we exclude
  ``conversation_chapters`` (the "最近" sidecar chapters).

* **No extra LLM call**.  We reuse ``momentary_state._matched_axes`` on
  the assistant messages cited by each distilled item.  When cited assistant
  text clearly expresses emotional or cognitive signals we mark ``known``;
  when it is clearly factual with no Honey-self signals we mark ``neutral``;
  when we cannot correlate any assistant reply we mark ``unknown``.

* **Sidecar on continuity.db** keyed by structured_memories.id.  The
  structured_memories row itself is never mutated; INSERT OR IGNORE keeps
  repeated distillations idempotent.

* **Bounded recall effect**.  The imprint is read-only at recall time.  It
  does not auto-update memory importance, does not inject G2 evidence, and
  does not bypass topic relevance or source permission.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from honeyos.companion.momentary_state import _matched_axes


logger = logging.getLogger(__name__)


STATUS_KNOWN = "known"
STATUS_NEUTRAL = "neutral"
STATUS_UNKNOWN = "unknown"

_VALENCE_LABEL = {
    "positive_valence": "positive",
    "negative_valence": "negative",
    "warmth": "warm",
    "tension": "tense",
    "playfulness": "playful",
    "seriousness": "serious",
    "energy": "energized",
    "curiosity": "curious",
    "reflectiveness": "reflective",
}

_ELIGIBLE_KINDS = frozenset({"episode", "commitment", "open_loop"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EmotionalImprint:
    memory_id: str
    lane_key: str
    kind: str
    status: str
    dominant_axis: str | None
    dominant_label: str | None
    basis_axes: tuple[str, ...]
    basis_turn_ids: tuple[int, ...]
    formed_at: str | None
    recorded_at: str
    distillation_run_id: str | None
    evidence_summary: str


class EmotionalImprintStore:
    """Append-only sidecar table on continuity.db, keyed by structured_memories.id."""

    TABLE = "structured_memory_emotional_imprints"

    def __init__(self, home: Path | str) -> None:
        self.home = Path(home).expanduser().resolve()
        self.db_path = self.home / "continuity.db"

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=1.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _ensure_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                memory_id TEXT PRIMARY KEY,
                lane_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('known','neutral','unknown')),
                dominant_axis TEXT,
                dominant_label TEXT,
                basis_axes_json TEXT NOT NULL DEFAULT '[]',
                basis_turn_ids_json TEXT NOT NULL DEFAULT '[]',
                formed_at TEXT,
                recorded_at TEXT NOT NULL,
                distillation_run_id TEXT,
                evidence_summary TEXT NOT NULL DEFAULT ''
            )
            """
        )

    # ── write ──────────────────────────────────────────────────────────────

    def upsert_for_distillation(
        self,
        *,
        distillation_run_id: str,
        job_messages: Sequence[Mapping[str, Any]],
        applied_memory_ids: Sequence[str],
        lane_key: str,
    ) -> int:
        """Attach imprints to every structured memory row created by this run.

        ``applied_memory_ids`` must be the concrete structured_memories.id
        values written in this batch.  Rows that already have an imprint
        are never rewritten (INSERT OR IGNORE); repeated distillations on
        the same source batch therefore remain idempotent.
        """
        if not applied_memory_ids:
            return 0

        by_row_id: dict[int, Mapping[str, Any]] = {}
        for message in job_messages:
            try:
                row_id = int(message["_row_id"])
            except (TypeError, KeyError, ValueError):
                continue
            by_row_id[row_id] = message

        created = 0
        try:
            with self._connect() as connection:
                self._ensure_table(connection)
                connection.execute("BEGIN IMMEDIATE")
                for memory_id in applied_memory_ids:
                    row = connection.execute(
                        """
                        SELECT id, kind, source_message_ids, created_at
                        FROM structured_memories WHERE id = ?
                        """,
                        (memory_id,),
                    ).fetchone()
                    if row is None:
                        continue
                    kind = str(row["kind"] or "").strip().lower()
                    existing = connection.execute(
                        f"SELECT memory_id FROM {self.TABLE} WHERE memory_id = ?",
                        (memory_id,),
                    ).fetchone()
                    if existing is not None:
                        continue

                    if kind not in _ELIGIBLE_KINDS:
                        self._insert_row(
                            connection,
                            memory_id=memory_id,
                            lane_key=lane_key,
                            kind=kind,
                            status=STATUS_UNKNOWN,
                            dominant_axis=None,
                            dominant_label=None,
                            basis_axes=(),
                            basis_turn_ids=(),
                            formed_at=None,
                            distillation_run_id=distillation_run_id,
                            evidence_summary=(
                                f"kind={kind} not an event Honey experienced "
                                "(user transient state or system artifact)"
                            ),
                        )
                        continue

                    basis_axes, basis_turn_ids, formed_at = self._infer_basis(
                        row, by_row_id
                    )
                    status, dominant_axis, dominant_label, summary = self._classify(
                        basis_axes, basis_turn_ids
                    )
                    self._insert_row(
                        connection,
                        memory_id=memory_id,
                        lane_key=lane_key,
                        kind=kind,
                        status=status,
                        dominant_axis=dominant_axis,
                        dominant_label=dominant_label,
                        basis_axes=basis_axes,
                        basis_turn_ids=basis_turn_ids,
                        formed_at=formed_at,
                        distillation_run_id=distillation_run_id,
                        evidence_summary=summary,
                    )
                    created += 1
        except (sqlite3.Error, ValueError, TypeError, OSError):
            logger.exception("emotional imprint sidecar write failed")
            return created
        return created

    def _infer_basis(
        self,
        memory_row: sqlite3.Row,
        by_row_id: dict[int, Mapping[str, Any]],
    ) -> tuple[tuple[str, ...], tuple[int, ...], str | None]:
        try:
            cited_ids = tuple(
                int(v) for v in json.loads(memory_row["source_message_ids"] or "[]")
                if int(v) > 0
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            cited_ids = ()

        assistant_rows: list[Mapping[str, Any]] = []
        for row_id in cited_ids:
            msg = by_row_id.get(row_id)
            if msg is not None and str(msg.get("role") or "").strip().lower() == "assistant":
                assistant_rows.append(msg)

        if assistant_rows:
            formed_at = max(
                str(msg.get("created_at") or msg.get("_created_at") or "").strip()
                for msg in assistant_rows
                if msg.get("created_at") or msg.get("_created_at")
            ) or None
        else:
            raw = str(memory_row["created_at"] or "").strip()
            formed_at = raw or None

        axes_acc: list[str] = []
        for msg in assistant_rows:
            axes_acc.extend(sorted(_matched_axes(str(msg.get("content") or ""))))
        basis_axes = tuple(dict.fromkeys(axes_acc))
        basis_turn_ids = tuple(dict.fromkeys(int(msg["_row_id"]) for msg in assistant_rows))
        return basis_axes, basis_turn_ids, formed_at

    @staticmethod
    def _classify(
        basis_axes: tuple[str, ...],
        basis_turn_ids: tuple[int, ...],
    ) -> tuple[str, str | None, str | None, str]:
        """Classify using S4.5 stricter evidence rules.

        ``known`` requires Honey-self emotional/cognitive signals actually
        matched in assistant text.  ``neutral`` is **not** the absence of
        signals — it requires a distinct, verifiable low-arousal basis we
        do not yet produce here.  This S4.5 refactor therefore returns
        ``unknown`` whenever we lack concrete evidence, instead of
        collapsing the "found assistant text but no emotion signal" case
        into ``neutral``.  ``neutral`` remains a valid status in the
        CHECK constraint so future versions can emit it safely.
        """
        if basis_axes:
            for candidate in ("positive_valence", "negative_valence",
                              "warmth", "tension", "playfulness",
                              "seriousness", "energy", "curiosity",
                              "reflectiveness"):
                if candidate in basis_axes:
                    dominant = candidate
                    break
            else:
                dominant = basis_axes[0]
            label = _VALENCE_LABEL.get(dominant)
            summary = (
                f"Cited assistant replies showed observable "
                f"{label or dominant or 'self-reported'} signals."
            )
            return STATUS_KNOWN, dominant, label, summary

        if not basis_turn_ids:
            return (
                STATUS_UNKNOWN, None, None,
                "No assistant reply could be linked to this memory item."
            )
        # S4.5: absence of matched emotion signal does NOT mean the event
        # was neutral — it means we do not know.  Keep neutral reserved for
        # a future version that can produce verifiable low-arousal evidence.
        return (
            STATUS_UNKNOWN, None, None,
            "Cited assistant text exists but no Honey-self emotional or "
            "cognitive signal could be confirmed from the transcript."
        )

    def _insert_row(
        self,
        connection: sqlite3.Connection,
        *,
        memory_id: str,
        lane_key: str,
        kind: str,
        status: str,
        dominant_axis: str | None,
        dominant_label: str | None,
        basis_axes: tuple[str, ...],
        basis_turn_ids: tuple[int, ...],
        formed_at: str | None,
        distillation_run_id: str | None,
        evidence_summary: str,
    ) -> None:
        recorded_at = _now()
        connection.execute(
            f"""
            INSERT OR IGNORE INTO {self.TABLE} (
                memory_id, lane_key, kind, status,
                dominant_axis, dominant_label,
                basis_axes_json, basis_turn_ids_json,
                formed_at, recorded_at, distillation_run_id, evidence_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id, lane_key, kind, status,
                dominant_axis, dominant_label,
                json.dumps(list(basis_axes), separators=(",", ":")),
                json.dumps(list(basis_turn_ids), separators=(",", ":")),
                formed_at, recorded_at,
                distillation_run_id or "",
                evidence_summary,
            ),
        )

    # ── read ──────────────────────────────────────────────────────────────

    def get(self, memory_id: str) -> EmotionalImprint | None:
        try:
            with self._connect() as connection:
                self._ensure_table(connection)
                row = connection.execute(
                    f"SELECT * FROM {self.TABLE} WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
        except sqlite3.Error:
            return None
        if row is None:
            return None
        return self._row_to_imprint(row)

    def _row_to_imprint(self, row: sqlite3.Row) -> EmotionalImprint:
        try:
            basis_axes = tuple(json.loads(row["basis_axes_json"] or "[]"))
        except Exception:
            basis_axes = ()
        try:
            basis_turn_ids = tuple(
                int(v) for v in json.loads(row["basis_turn_ids_json"] or "[]")
            )
        except Exception:
            basis_turn_ids = ()
        return EmotionalImprint(
            memory_id=row["memory_id"],
            lane_key=row["lane_key"],
            kind=row["kind"],
            status=row["status"],
            dominant_axis=row["dominant_axis"] or None,
            dominant_label=row["dominant_label"] or None,
            basis_axes=basis_axes,
            basis_turn_ids=basis_turn_ids,
            formed_at=row["formed_at"] or None,
            recorded_at=row["recorded_at"],
            distillation_run_id=row["distillation_run_id"] or None,
            evidence_summary=row["evidence_summary"] or "",
        )


# ── Hook factory ───────────────────────────────────────────────────────────

def _applied_ids_for_run(home: Path, run_id: str) -> tuple[str, ...]:
    """Return structured_memories.id values whose distillation_run_id matches."""
    try:
        conn = sqlite3.connect(home / "continuity.db", timeout=1.0)
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT id FROM structured_memories
                WHERE distillation_run_id = ?
                """,
                (run_id,),
            ).fetchall()
        finally:
            conn.close()
    except sqlite3.Error:
        return ()
    return tuple(str(r[0]) for r in rows)


def emotion_imprint_hook_factory(
    *,
    home: Path | str,
    downstream_holder: list[Callable[..., Any] | None] | None = None,
) -> Callable[..., Any]:
    """Build a MemoryDistiller post_completed_hook that writes imprints.

    ``downstream_holder`` — if given — must be a one-element mutable list
    where the caller writes a downstream callable before the next
    distillation completes.  The hook checks this list **every time** so
    the downstream (typically the U2 producer) can be hot-enabled or
    disabled without requiring the emotion hook itself to be rebound.

    The returned closure is therefore stable for the lifetime of the
    distiller; callers construct it once and never replace it.  Emotion
    imprinting itself is idempotent (INSERT OR IGNORE) and fail-open so
    repeated invocations are safe.
    """
    home_path = Path(home).expanduser().resolve()
    store = EmotionalImprintStore(home_path)

    def _hook(*, job: Any, result: Any, main_runtime: Any = None, **_kwargs: Any) -> Any:
        # Emotion imprint path — fail-open, runs before any downstream.
        try:
            if result is None or getattr(result, "status", None) != "completed":
                return
            applied_count = int(getattr(result, "applied", 0) or 0)
            if applied_count == 0:
                return
            run_id = str(getattr(job, "run_id", "") or "")
            lane = str(getattr(job, "lane_key", "") or "")
            applied_ids = _applied_ids_for_run(home_path, run_id)
            if not applied_ids:
                return
            created = store.upsert_for_distillation(
                distillation_run_id=run_id,
                job_messages=tuple(getattr(job, "messages", ()) or ()),
                applied_memory_ids=applied_ids,
                lane_key=lane,
            )
            if created:
                logger.debug(
                    "emotion imprint sidecar: %d rows written for run %s",
                    created, run_id,
                )
        except Exception:
            logger.exception("emotion imprint hook failed")

        # Downstream — looked up fresh from the holder on every call so
        # the U2 producer can be hot-wired / unwired without replacing
        # the emotion hook closure.
        #
        # The downstream may be sync (legacy) or async (the U2 same-batch
        # producer). Return whatever it produces so MemoryDistiller can await
        # an awaitable; dropping a coroutine here would silently skip U2.
        if downstream_holder is not None and len(downstream_holder) >= 1:
            downstream = downstream_holder[0]
            if downstream is not None:
                try:
                    return downstream(
                        job=job, result=result, main_runtime=main_runtime, **_kwargs
                    )
                except Exception:
                    logger.exception("downstream hook failed after emotion")
        return None

    return _hook
