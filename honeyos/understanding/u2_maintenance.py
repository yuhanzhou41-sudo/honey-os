"""Deterministic label maintenance; the model never sets grade or state."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .u2_contracts import EvidenceGrade, LabelState, Proposal
from .u2_search import index_label
from .u2_store import UnderstandingStore

# Continuity memory kinds eligible to serve as U2 evidence. Kept in sync with
# gateway._honeyos_u2_evidence_meta and the graph read filter so a label can
# never rest on a forgotten / archived / ineligible source.
_EVIDENCE_KINDS = frozenset({"episode", "commitment"})


def _label_id(owner: str, lane: str, namespace: str, proposal: Proposal) -> str:
    raw = "\0".join((owner, lane, namespace, proposal.category_id,
                     proposal.scope_key, proposal.canonical_key))
    return "ul_" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def _grade(event_count: int, session_count: int, span_days: int,
           counter_count: int) -> tuple[EvidenceGrade, LabelState]:
    if counter_count:
        return EvidenceGrade.LOW, LabelState.DISPUTED
    if event_count >= 4 and session_count >= 3 and span_days >= 7:
        return EvidenceGrade.HIGH, LabelState.SUPPORTED
    if event_count >= 2 and session_count >= 2:
        return EvidenceGrade.MEDIUM, LabelState.SUPPORTED
    return EvidenceGrade.LOW, LabelState.TENTATIVE


def _continuity_active_ids(db_path, ids) -> set[str]:
    """Return the subset of continuity memory ids still active + U2-eligible."""
    ids = [str(i) for i in ids if i]
    if not ids:
        return set()
    path = Path(db_path)
    if not path.is_file():
        return set()
    try:
        uri = path.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=1.0) as db:
            placeholders = ",".join("?" for _ in ids)
            rows = db.execute(
                f"SELECT id FROM structured_memories WHERE id IN ({placeholders}) "
                "AND status='active' AND kind IN ('episode','commitment')", ids,
            ).fetchall()
        return {str(row[0]) for row in rows}
    except sqlite3.Error:
        return set()


def _valid_evidence_rows(db: sqlite3.Connection, label_id: str,
                         continuity_db_path=None) -> tuple[list, list[str]]:
    """Return (rows used for grading, orphan refs that should be pruned).

    When ``continuity_db_path`` is provided, evidence pointing at a continuity
    memory that is no longer active/eligible is excluded from grading and
    reported as an orphan so the caller can prune it. Non-continuity refs are
    trusted (the current store only ever writes ``continuity:`` refs), which
    keeps recovery / unit tests that pass raw refs grading deterministically.
    """
    rows = db.execute(
        "SELECT evidence_ref,event_group,session_ref,relation,occurred_at "
        "FROM evidence WHERE label_id=? ORDER BY relation,evidence_ref",
        (label_id,),
    ).fetchall()
    if not continuity_db_path:
        return list(rows), []
    active = _continuity_active_ids(
        continuity_db_path,
        [str(r["evidence_ref"]).split(":", 1)[1]
         for r in rows if str(r["evidence_ref"]).startswith("continuity:")],
    )
    valid, orphans = [], []
    for row in rows:
        ref = str(row["evidence_ref"] or "")
        if ref.startswith("continuity:"):
            if ref.split(":", 1)[1] in active:
                valid.append(row)
            else:
                orphans.append(ref)
        else:
            valid.append(row)
    return valid, orphans


def _grade_from_rows(rows) -> tuple[EvidenceGrade, LabelState]:
    support = {row["event_group"] for row in rows if row["relation"] == "support"}
    counters = {row["event_group"] for row in rows if row["relation"] == "counter"}
    sessions = {row["session_ref"] for row in rows
                if row["relation"] == "support" and row["session_ref"]}
    dates = [datetime.fromisoformat(row["occurred_at"]) for row in rows
             if row["relation"] == "support" and row["occurred_at"]]
    span = (max(dates) - min(dates)).days if len(dates) > 1 else 0
    return _grade(len(support), len(sessions), span, len(counters))


def _archive_current(db: sqlite3.Connection, label_id: str, actor: str,
                     now: str) -> None:
    """Snapshot the current label row into label_versions before mutating it.

    The timeline table may not exist in stores created before S4.5 (or in
    minimal fixtures that build the schema by hand); create it lazily so a
    re-evaluation can never fail just because the version table is absent.
    """
    db.execute("""CREATE TABLE IF NOT EXISTS label_versions(
        label_id TEXT NOT NULL REFERENCES labels(id), revision INTEGER NOT NULL,
        body TEXT NOT NULL, state TEXT NOT NULL, grade TEXT NOT NULL,
        actor TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY(label_id,revision))""")
    db.execute(
        "INSERT OR IGNORE INTO label_versions "
        "(label_id,revision,body,state,grade,actor,created_at) "
        "SELECT id,revision,body,state,grade,?,? FROM labels WHERE id=?",
        (actor, now, label_id),
    )


def apply_proposal(store: UnderstandingStore, *, owner: str, lane: str,
                   namespace: str, proposal: Proposal,
                   evidence_meta: dict[str, tuple[str, str, str, str | None]],
                   continuity_db_path=None) -> str:
    """Apply one validated proposal atomically.

    evidence_meta maps ref -> (event_group, session_ref, source_revision,
    occurred_at_iso). Missing refs are rejected before any write.

    When ``continuity_db_path`` is supplied, the post-write grade/state is
    derived only from evidence whose continuity source is still active and
    eligible; orphaned rows (forgotten / archived source) are pruned so a
    withdrawn source can never keep inflating a label's confidence.
    """
    refs = proposal.support_refs + proposal.counter_refs
    if not set(refs).issubset(evidence_meta):
        raise ValueError("missing evidence metadata")
    label_id = _label_id(owner, lane, namespace, proposal)
    now = datetime.now(timezone.utc).isoformat()
    with store.connect() as db:
        existing = db.execute("SELECT * FROM labels WHERE id=?", (label_id,)).fetchone()
        epoch_row = db.execute("SELECT value FROM meta WHERE key='policy_epoch'").fetchone()
        epoch = int(epoch_row[0]) if epoch_row else 0
        if existing and existing["state"] == LabelState.USER_SUPPRESSED:
            raise PermissionError("suppressed label cannot be revived")
        if existing and existing["body"] == proposal.text:
            prior = db.execute("""SELECT evidence_ref,relation FROM evidence
                WHERE label_id=?""", (label_id,)).fetchall()
            prior_pairs = {(row["evidence_ref"], row["relation"]) for row in prior}
            requested_pairs = (
                {(ref, "support") for ref in proposal.support_refs}
                | {(ref, "counter") for ref in proposal.counter_refs}
            )
            if requested_pairs.issubset(prior_pairs):
                # Crash recovery may replay an already-applied response before
                # the job completion receipt committed. Do not create a fake
                # revision or strengthen evidence on that replay.
                return label_id
        revision = int(existing["revision"]) + 1 if existing else 1
        db.execute("""INSERT INTO labels
            (id,owner,lane,namespace,category,scope_key,canonical_key,body,state,grade,
             revision,policy_epoch,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET body=excluded.body,revision=excluded.revision,
              updated_at=excluded.updated_at""",
            (label_id, owner, lane, namespace, proposal.category_id, proposal.scope_key,
             proposal.canonical_key, proposal.text, LabelState.TENTATIVE,
             EvidenceGrade.LOW, revision, epoch,
             existing["created_at"] if existing else now, now))
        for relation, relation_refs in (("support", proposal.support_refs),
                                        ("counter", proposal.counter_refs)):
            for ref in relation_refs:
                group, session, source_revision, occurred = evidence_meta[ref]
                db.execute("""INSERT OR IGNORE INTO evidence
                  (label_id,evidence_ref,event_group,session_ref,relation,occurred_at,source_revision)
                  VALUES(?,?,?,?,?,?,?)""",
                  (label_id, ref, group, session, relation, occurred, source_revision))
        valid_rows, orphan_refs = _valid_evidence_rows(db, label_id, continuity_db_path)
        for ref in orphan_refs:
            db.execute(
                "DELETE FROM evidence WHERE label_id=? AND evidence_ref=?",
                (label_id, ref),
            )
        grade, state = _grade_from_rows(valid_rows)
        db.execute("UPDATE labels SET grade=?,state=?,updated_at=? WHERE id=?",
                   (grade, state, now, label_id))
    index_label(store, label_id, owner, lane, namespace,
                f"{proposal.category_id} {proposal.scope_key} {proposal.canonical_key} {proposal.text}")
    return label_id


def recompute_label(store: UnderstandingStore, label_id: str, *,
                    continuity_db_path, actor: str = "recompute") -> dict:
    """Re-evaluate one label's grade/state from currently-valid evidence.

    Prunes evidence rows whose continuity source is no longer active/eligible,
    then re-derives grade/state with the existing ``_grade`` rules. Never
    revives or edits a user-suppressed label. A label_versions row is written
    only when something actually changed, so the UI timeline can show the
    re-evaluation without noise.
    """
    with store.connect() as db:
        row = db.execute(
            "SELECT state,grade,revision FROM labels WHERE id=?", (label_id,),
        ).fetchone()
        if row is None:
            return {"changed": False, "label_id": label_id, "reason": "not_found"}
        if row["state"] == LabelState.USER_SUPPRESSED:
            return {"changed": False, "label_id": label_id,
                    "reason": "user_suppressed"}
        valid_rows, orphan_refs = _valid_evidence_rows(db, label_id, continuity_db_path)
        for ref in orphan_refs:
            db.execute(
                "DELETE FROM evidence WHERE label_id=? AND evidence_ref=?",
                (label_id, ref),
            )
        grade, state = _grade_from_rows(valid_rows)
        changed = (grade != row["grade"]) or (state != row["state"]) or bool(orphan_refs)
        if changed:
            now = datetime.now(timezone.utc).isoformat()
            _archive_current(db, label_id, actor, now)
            db.execute(
                "UPDATE labels SET grade=?,state=?,revision=revision+1,updated_at=? WHERE id=?",
                (grade, state, now, label_id),
            )
        return {"changed": changed, "label_id": label_id, "state": state,
                "grade": grade, "pruned": orphan_refs}


def recompute_labels_for_memory(store: UnderstandingStore, *,
                                continuity_db_path, memory_id) -> list[dict]:
    """Recompute every label citing one continuity memory after it changes."""
    ref = f"continuity:{memory_id}"
    with store.connect() as db:
        label_ids = [str(r["label_id"]) for r in db.execute(
            "SELECT DISTINCT label_id FROM evidence WHERE evidence_ref=?",
            (ref,),
        ).fetchall()]
    return [
        recompute_label(store, label_id, continuity_db_path=continuity_db_path,
                        actor="source_withdrawal")
        for label_id in label_ids
    ]


def reconcile_store(store: UnderstandingStore, *, continuity_db_path) -> dict:
    """Sweep all labels and re-evaluate against the live continuity source.

    Catches evidence whose source was archived, forgotten, or deleted outside
    the targeted hooks (e.g. background expiration of an eligible memory).
    User-suppressed labels are skipped. Returns scan/change counts.
    """
    with store.connect() as db:
        label_ids = [str(r["id"]) for r in db.execute(
            "SELECT id FROM labels WHERE state<>?", (LabelState.USER_SUPPRESSED,),
        ).fetchall()]
    changed = 0
    for label_id in label_ids:
        if recompute_label(store, label_id,
                           continuity_db_path=continuity_db_path).get("changed"):
            changed += 1
    return {"scanned": len(label_ids), "changed": changed}
