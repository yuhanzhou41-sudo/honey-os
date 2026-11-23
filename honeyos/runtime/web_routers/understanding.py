"""S4.5 user-understanding graph API.

Read-only graph inspection plus the minimal user-control verbs (suppress /
forget a tag, detach one evidence relation). Every handler is scoped to the
authenticated local owner and never returns the body of a user-suppressed
label. Forgotten native memories never surface because evidence is filtered
against ``structured_memories.status = 'active'``.

Data lives in two SQLite files under the HoneyOS home:
  * ``understanding_v2.db`` — labels / evidence (U2 tags)
  * ``continuity.db``       — structured_memories + S4 emotional imprints
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()

_LOCAL_OWNER = "local-owner"
_U2_DB = "understanding_v2.db"
_CONTINUITY_DB = "continuity.db"


def _home() -> Any:
    from honeyos.core.constants import get_honeyos_home

    return get_honeyos_home()


def _connect(path) -> sqlite3.Connection | None:
    from pathlib import Path

    db_path = Path(path)
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(db_path, timeout=1.0)
    conn.row_factory = sqlite3.Row
    return conn


def _memory_lookup(home) -> dict[str, dict[str, Any]]:
    """Map continuity memory id -> {kind,status,created_at,content,imprint}."""
    out: dict[str, dict[str, Any]] = {}
    conn = _connect(home / _CONTINUITY_DB)
    if conn is None:
        return out
    try:
        rows = conn.execute(
            "SELECT id, kind, status, content, created_at, "
            "source_session_id FROM structured_memories"
        ).fetchall()
        imprints: dict[str, sqlite3.Row] = {}
        try:
            for row in conn.execute(
                "SELECT memory_id, status, dominant_axis, dominant_label, "
                "formed_at FROM structured_memory_emotional_imprints"
            ).fetchall():
                imprints[str(row["memory_id"])] = row
        except sqlite3.Error:
            imprints = {}
        for row in rows:
            if str(row["status"] or "") != "active":
                continue
            imprint = imprints.get(str(row["id"]))
            out[str(row["id"])] = {
                "kind": str(row["kind"] or ""),
                "created_at": str(row["created_at"] or ""),
                "content": str(row["content"] or ""),
                "source_session_id": str(row["source_session_id"] or ""),
                "imprint": (
                    {
                        "status": str(imprint["status"] or ""),
                        "axis": imprint["dominant_axis"],
                        "label": imprint["dominant_label"],
                        "formed_at": imprint["formed_at"],
                    }
                    if imprint is not None else None
                ),
            }
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return out


def _evidence_for(conn: sqlite3.Connection, label_id: str,
                  memories: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    rows = conn.execute(
        "SELECT evidence_ref, relation, occurred_at, source_revision "
        "FROM evidence WHERE label_id=? ORDER BY relation, evidence_ref",
        (label_id,),
    ).fetchall()
    for row in rows:
        ref = str(row["evidence_ref"] or "")
        memory: dict[str, Any] | None = None
        if ref.startswith("continuity:"):
            memory = memories.get(ref.split(":", 1)[1])
            if memory is None:
                continue  # forgotten / missing native memory -> drop relation
        items.append({
            "ref": ref,
            "relation": str(row["relation"] or ""),
            "occurred_at": row["occurred_at"],
            "source_revision": row["source_revision"],
            "memory": memory,
        })
    return items


def _label_row(row: sqlite3.Row) -> dict[str, Any]:
    state = str(row["state"] or "")
    suppressed = state == "user_suppressed"
    return {
        "id": str(row["id"]),
        "category_id": str(row["category"] or ""),
        "scope_key": str(row["scope_key"] or ""),
        "canonical_key": str(row["canonical_key"] or ""),
        # Never leak the body of a user-suppressed label.
        "text": "" if suppressed else str(row["body"] or ""),
        "state": state,
        "grade": str(row["grade"] or ""),
        "revision": int(row["revision"] or 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "suppressed": suppressed,
    }


@router.get("/api/understanding/graph")
def get_understanding_graph(
    lane: str = Query("", description="Optional lane filter"),
    namespace: str = Query("", description="Optional namespace filter"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    home = _home()
    conn = _connect(home / _U2_DB)
    if conn is None:
        return {"labels": [], "total": 0, "owner": _LOCAL_OWNER}
    try:
        clauses = ["owner=?"]
        params: list[Any] = [_LOCAL_OWNER]
        if lane:
            clauses.append("lane=?")
            params.append(lane)
        if namespace:
            clauses.append("namespace=?")
            params.append(namespace)
        where = " AND ".join(clauses)
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM labels WHERE {where}", params,
        ).fetchone()["n"]
        rows = conn.execute(
            f"SELECT * FROM labels WHERE {where} "
            "ORDER BY updated_at DESC, id LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        memories = _memory_lookup(home)
        labels = []
        for row in rows:
            label = _label_row(row)
            label["evidence"] = _evidence_for(conn, label["id"], memories)
            labels.append(label)
        return {"labels": labels, "total": int(total), "owner": _LOCAL_OWNER}
    finally:
        conn.close()


@router.get("/api/understanding/labels/{label_id}")
def get_understanding_label(label_id: str) -> dict[str, Any]:
    home = _home()
    conn = _connect(home / _U2_DB)
    if conn is None:
        raise HTTPException(status_code=404, detail="understanding store not found")
    try:
        row = conn.execute(
            "SELECT * FROM labels WHERE id=? AND owner=?", (label_id, _LOCAL_OWNER),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="label not found")
        label = _label_row(row)
        label["evidence"] = _evidence_for(conn, label_id, _memory_lookup(home))
        return label
    finally:
        conn.close()


@router.post("/api/understanding/labels/{label_id}/suppress")
def suppress_understanding_label(label_id: str) -> dict[str, Any]:
    """User forgets a tag: it stops being used/revived but native memories stay."""
    home = _home()
    conn = _connect(home / _U2_DB)
    if conn is None:
        raise HTTPException(status_code=404, detail="understanding store not found")
    try:
        cur = conn.execute(
            "UPDATE labels SET state='user_suppressed' "
            "WHERE id=? AND owner=?",
            (label_id, _LOCAL_OWNER),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="label not found")
        return {"ok": True, "label_id": label_id, "state": "user_suppressed"}
    finally:
        conn.close()


@router.delete("/api/understanding/labels/{label_id}/evidence")
def detach_understanding_evidence(
    label_id: str, ref: str = Query(..., description="Evidence ref to detach"),
) -> dict[str, Any]:
    """Remove ONE tag<->memory relation without deleting either node."""
    home = _home()
    conn = _connect(home / _U2_DB)
    if conn is None:
        raise HTTPException(status_code=404, detail="understanding store not found")
    try:
        cur = conn.execute(
            "DELETE FROM evidence WHERE label_id=? AND evidence_ref=?",
            (label_id, ref),
        )
        conn.commit()
        return {"ok": True, "label_id": label_id, "removed": int(cur.rowcount)}
    finally:
        conn.close()
