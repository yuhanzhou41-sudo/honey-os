"""Persistently prioritize memories related to active Study plans."""

from __future__ import annotations

from datetime import datetime, timezone

from honeyos.core.constants import get_honeyos_home
from honeyos.memory.repository import CognitiveMemoryRepository
from honeyos.memory.runtime_shadow import _query_terms, _score
from honeyos.memory.salience import set_memory_salience

from .models import StudyPlanStatus
from .repository import StudyRepository


_ACTIVE_USER_EMPHASIS = 0.85
_ACTIVE_RECALL_AFFINITY = 0.9
_BOOST_TABLE = """
CREATE TABLE IF NOT EXISTS study_plan_salience_boosts (
    plan_id TEXT NOT NULL,
    memory_kind TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    previous_user_emphasis REAL NOT NULL,
    previous_recall_affinity REAL NOT NULL,
    boosted_user_emphasis REAL NOT NULL,
    boosted_recall_affinity REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(plan_id, memory_kind, memory_id)
)
"""


def _plan_signals(plan):
    fragments = [plan.title, *plan.goals]
    for task in plan.tasks:
        fragments.extend((task.title, task.description))
    return (
        plan.id,
        {plan.id, *(task.id for task in plan.tasks)},
        [_query_terms(fragment) for fragment in fragments if fragment.strip()],
    )


def _related(signals, memory) -> bool:
    source_key = str(memory["source_key"] or "")
    if source_key and source_key in signals[1]:
        return True
    summary = str(memory["summary"] or "")
    return any(_score(summary, terms)[0] >= 3.0 for terms in signals[2])


def _restore_previous(db, rows) -> int:
    restored = 0
    for row in rows:
        current = db.execute(
            "SELECT user_emphasis,recall_affinity FROM memory_salience "
            "WHERE memory_kind=? AND memory_id=?",
            (row["memory_kind"], row["memory_id"]),
        ).fetchone()
        if current is None:
            continue
        values = {}
        for field in ("user_emphasis", "recall_affinity"):
            if current[field] == row[f"boosted_{field}"]:
                values[field] = row[f"previous_{field}"]
        if values:
            set_memory_salience(
                db, row["memory_kind"], row["memory_id"], **values,
            )
            restored += 1
    return restored


def sync_active_study_memory_salience(
    study_repository: StudyRepository | None = None,
    memory_repository: CognitiveMemoryRepository | None = None,
    *,
    home=None,
) -> dict:
    """Reconcile persistent boosts and restore their exact prior values.

    The boost ledger lives in the cognitive database, so restoring old boosts,
    writing new salience and recording the new ledger share one transaction.
    """
    root = home or get_honeyos_home()
    study = study_repository or StudyRepository(root)
    memory = memory_repository or CognitiveMemoryRepository(root)
    active = [
        plan for plan in study.list_plans()
        if plan.status is StudyPlanStatus.ACTIVE
    ]
    signals = [_plan_signals(plan) for plan in active]
    now = datetime.now(timezone.utc).isoformat()
    with memory.connect() as db:
        db.execute(_BOOST_TABLE)
        previous = db.execute("SELECT * FROM study_plan_salience_boosts").fetchall()
        restored = _restore_previous(db, previous)
        db.execute("DELETE FROM study_plan_salience_boosts")
        matched = {}
        if active:
            rows = db.execute(
                "SELECT episode_id,summary,source_key FROM memory_episodes "
                "WHERE status='active'"
            ).fetchall()
            for row in rows:
                plan_ids = [signal[0] for signal in signals if _related(signal, row)]
                if plan_ids:
                    matched[row["episode_id"]] = plan_ids
        boosted = 0
        for memory_id, plan_ids in matched.items():
            current = db.execute(
                "SELECT user_emphasis,recall_affinity FROM memory_salience "
                "WHERE memory_kind='episode' AND memory_id=?", (memory_id,),
            ).fetchone()
            old_emphasis = float(current["user_emphasis"] or 0) if current else 0.0
            old_affinity = float(current["recall_affinity"] or 0) if current else 0.0
            new_emphasis = max(old_emphasis, _ACTIVE_USER_EMPHASIS)
            new_affinity = max(old_affinity, _ACTIVE_RECALL_AFFINITY)
            if (new_emphasis, new_affinity) == (old_emphasis, old_affinity):
                continue
            set_memory_salience(
                db, "episode", memory_id,
                user_emphasis=new_emphasis, recall_affinity=new_affinity,
            )
            boosted += 1
            db.executemany(
                "INSERT INTO study_plan_salience_boosts VALUES (?,?,?,?,?,?,?,?)",
                [
                    (plan_id, "episode", memory_id, old_emphasis, old_affinity,
                     new_emphasis, new_affinity, now)
                    for plan_id in plan_ids
                ],
            )
    return {
        "active_plans": len(active), "matched_memories": len(matched),
        "boosted_memories": boosted, "restored_memories": restored,
    }
