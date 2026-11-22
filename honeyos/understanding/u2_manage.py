"""Immediate suppression/forget management operations."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .u2_contracts import LabelState
from .u2_store import UnderstandingStore


def _scoped_label(db, label_id: str, *, owner: str | None = None,
                  lane: str | None = None, namespace: str | None = None):
    row = db.execute("SELECT * FROM labels WHERE id=?", (label_id,)).fetchone()
    if row is None:
        raise KeyError(label_id)
    expected = (("owner", owner), ("lane", lane), ("namespace", namespace))
    if any(value is not None and row[key] != value for key, value in expected):
        raise PermissionError("label is outside the authenticated scope")
    return row


def _archive(db, row, actor: str) -> None:
    db.execute("""INSERT OR IGNORE INTO label_versions
        (label_id,revision,body,state,grade,actor,created_at) VALUES(?,?,?,?,?,?,?)""",
        (row["id"], row["revision"], row["body"], row["state"], row["grade"],
         actor, datetime.now(timezone.utc).isoformat()))


def suppress(store: UnderstandingStore, label_id: str, *, owner: str | None = None,
             lane: str | None = None, namespace: str | None = None) -> int:
    with store.connect() as db:
        _scoped_label(db, label_id, owner=owner, lane=lane, namespace=namespace)
    epoch = store.bump_policy_epoch()
    with store.connect() as db:
        row = _scoped_label(db, label_id, owner=owner, lane=lane, namespace=namespace)
        _archive(db, row, "user_suppress")
        digest = hashlib.sha256(row["canonical_key"].encode()).hexdigest()
        db.execute("""INSERT OR REPLACE INTO suppressions VALUES(?,?,?,?,?,?,1,?)""",
                   (row["owner"], row["lane"], row["namespace"], row["category"],
                    row["scope_key"], digest, epoch))
        db.execute("UPDATE labels SET state=?,body='',policy_epoch=? WHERE id=?",
                   (LabelState.USER_SUPPRESSED, epoch, label_id))
    return epoch


def forget(store: UnderstandingStore, label_id: str, *, owner: str | None = None,
           lane: str | None = None, namespace: str | None = None) -> int:
    epoch = suppress(store, label_id, owner=owner, lane=lane, namespace=namespace)
    with store.connect() as db:
        db.execute("DELETE FROM evidence WHERE label_id=?", (label_id,))
        db.execute("DELETE FROM postings WHERE label_id=?", (label_id,))
    return epoch


def edit(store: UnderstandingStore, label_id: str, body: str, *, owner: str,
         lane: str, namespace: str) -> int:
    text = str(body).strip()
    if not text or len(text) > 360:
        raise ValueError("edited understanding must contain 1-360 characters")
    with store.connect() as db:
        _scoped_label(db, label_id, owner=owner, lane=lane, namespace=namespace)
    epoch = store.bump_policy_epoch()
    now = datetime.now(timezone.utc).isoformat()
    with store.connect() as db:
        row = _scoped_label(db, label_id, owner=owner, lane=lane, namespace=namespace)
        _archive(db, row, "user_edit")
        db.execute("""UPDATE labels SET body=?,state=?,grade='low',revision=revision+1,
            policy_epoch=?,updated_at=? WHERE id=?""",
            (text, LabelState.TENTATIVE, epoch, now, label_id))
    return epoch


def restore(store: UnderstandingStore, label_id: str, *, owner: str,
            lane: str, namespace: str) -> int:
    """Explicit restore: recheckable, low-grade, never inherits old confidence."""
    with store.connect() as db:
        row = _scoped_label(db, label_id, owner=owner, lane=lane, namespace=namespace)
        if row["state"] != LabelState.USER_SUPPRESSED:
            raise ValueError("only a suppressed label can be restored")
        version = db.execute("""SELECT body FROM label_versions
            WHERE label_id=? AND body<>'' ORDER BY revision DESC LIMIT 1""", (label_id,)).fetchone()
        if version is None:
            raise ValueError("source text unavailable; restore requires a new user edit")
    epoch = store.bump_policy_epoch()
    now = datetime.now(timezone.utc).isoformat()
    with store.connect() as db:
        row = _scoped_label(db, label_id, owner=owner, lane=lane, namespace=namespace)
        db.execute("""UPDATE suppressions SET active=0,policy_epoch=?
            WHERE owner=? AND lane=? AND namespace=? AND category=? AND scope_key=?""",
            (epoch, owner, lane, namespace, row["category"], row["scope_key"]))
        db.execute("""UPDATE labels SET body=?,state=?,grade='low',revision=revision+1,
            policy_epoch=?,updated_at=? WHERE id=?""",
            (version["body"], LabelState.NEEDS_REASSESSMENT, epoch, now, label_id))
    return epoch


def explain(store: UnderstandingStore, label_id: str, *, limit: int = 20,
            owner: str | None = None, lane: str | None = None,
            namespace: str | None = None) -> dict:
    with store.connect() as db:
        label = _scoped_label(db, label_id, owner=owner, lane=lane, namespace=namespace)
        evidence = db.execute("""SELECT evidence_ref,event_group,relation,source_revision
          FROM evidence WHERE label_id=? ORDER BY relation,evidence_ref LIMIT ?""",
          (label_id, min(limit, 20))).fetchall()
        versions = db.execute("""SELECT revision,state,grade,actor,created_at
          FROM label_versions WHERE label_id=? ORDER BY revision DESC LIMIT ?""",
          (label_id, min(limit, 20))).fetchall()
    evidence_payload = []
    for row in evidence:
        item = dict(row)
        # U2 stores lineage, not copied source text. Current source validity
        # must be rechecked by the owning resolver before content is shown.
        item["source_status"] = "recorded_unverified"
        evidence_payload.append(item)
    return {"label": dict(label), "evidence": evidence_payload,
            "versions": [dict(row) for row in versions]}
