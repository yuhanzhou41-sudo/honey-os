"""Deterministic label maintenance; the model never sets grade or state."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .u2_contracts import EvidenceGrade, LabelState, Proposal
from .u2_search import index_label
from .u2_store import UnderstandingStore


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


def apply_proposal(store: UnderstandingStore, *, owner: str, lane: str,
                   namespace: str, proposal: Proposal,
                   evidence_meta: dict[str, tuple[str, str, str, str | None]]) -> str:
    """Apply one validated proposal atomically.

    evidence_meta maps ref -> (event_group, session_ref, source_revision,
    occurred_at_iso). Missing refs are rejected before any write.
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
        rows = db.execute("SELECT event_group,session_ref,relation,occurred_at FROM evidence WHERE label_id=?",
                          (label_id,)).fetchall()
        support = {row["event_group"] for row in rows if row["relation"] == "support"}
        counters = {row["event_group"] for row in rows if row["relation"] == "counter"}
        sessions = {row["session_ref"] for row in rows if row["relation"] == "support" and row["session_ref"]}
        dates = [datetime.fromisoformat(row["occurred_at"]) for row in rows
                 if row["relation"] == "support" and row["occurred_at"]]
        span = (max(dates) - min(dates)).days if len(dates) > 1 else 0
        grade, state = _grade(len(support), len(sessions), span, len(counters))
        db.execute("UPDATE labels SET grade=?,state=?,updated_at=? WHERE id=?",
                   (grade, state, now, label_id))
    index_label(store, label_id, owner, lane, namespace,
                f"{proposal.category_id} {proposal.scope_key} {proposal.canonical_key} {proposal.text}")
    return label_id

