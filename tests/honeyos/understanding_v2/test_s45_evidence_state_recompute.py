"""S4.5 regression: U2 label grade/state must track live evidence.

Covers the four evidence-loss paths required by the scope:
  * detach one relation (graph API)   -> re-grade the label
  * forget a native memory (continuity)-> re-grade citing labels
  * counter evidence removed          -> revert DISPUTED -> SUPPORTED
  * source withdrawn / orphan rows    -> prune + re-grade, never revive a
     user-suppressed label.

All fixtures use isolated tmp databases and a fake model path (apply_proposal
directly); no real LLM, no production home.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.understanding.u2_contracts import Proposal
from honeyos.understanding.u2_maintenance import (
    apply_proposal,
    recompute_label,
    recompute_labels_for_memory,
    reconcile_store,
)
from honeyos.understanding.u2_manage import explain, suppress
from honeyos.understanding.u2_store import UnderstandingStore
from honeyos.runtime.web_routers.understanding import router as understanding_router

OWNER, LANE, NS = "local-owner", "lane", "general"


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _record_episodes(home: Path, count: int) -> list[str]:
    store = StructuredMemoryStore(home)
    ids: list[str] = []
    for i in range(count):
        item = store.record(
            lane_key=LANE, kind="episode", content=f"mechanism-first memory {i}",
            evidence="user_stated", source_session_id=f"sess-{i}",
            importance="high", created_by="background",
            now=datetime.now(timezone.utc) - timedelta(days=count - i),
        )
        assert item is not None
        ids.append(item.id)
    return ids


def _proposal(support_refs, counter_refs=()):
    return Proposal("propose", "interest_preference", "learning",
                    "mechanism_first", "似乎偏好先理解机制",
                    tuple(support_refs), tuple(counter_refs))


def _meta_for(ids, *, sessions=None, day_offsets=None):
    """Build evidence_meta for continuity refs with controlled grade inputs."""
    sessions = sessions or [f"sess-{i}" for i in range(len(ids))]
    day_offsets = day_offsets or [len(ids) - i for i in range(len(ids))]
    return {
        f"continuity:{mid}": (f"g{i}", sessions[i], "rev", _iso(day_offsets[i]))
        for i, mid in enumerate(ids)
    }


def _build_high_label(home: Path) -> tuple[str, list[str], UnderstandingStore]:
    """4 groups / 3 sessions / span 8d -> HIGH / SUPPORTED."""
    ids = _record_episodes(home, 4)
    meta = _meta_for(ids, sessions=["sA", "sA", "sB", "sC"],
                     day_offsets=[8, 6, 4, 0])
    store = UnderstandingStore(home / "understanding_v2.db")
    store.initialize()
    label_id = apply_proposal(
        store, owner=OWNER, lane=LANE, namespace=NS,
        proposal=_proposal([f"continuity:{i}" for i in ids]),
        evidence_meta=meta, continuity_db_path=home / "continuity.db",
    )
    row = explain(store, label_id)["label"]
    assert row["grade"] == "high" and row["state"] == "supported"
    return label_id, ids, store


def _evidence_count(store, label_id: str) -> int:
    with store.connect() as db:
        return db.execute(
            "SELECT COUNT(*) FROM evidence WHERE label_id=?", (label_id,),
        ).fetchone()[0]


def test_forget_source_downgrades_grade_and_prunes_orphan(tmp_path):
    label_id, ids, store = _build_high_label(tmp_path)
    c_store = StructuredMemoryStore(tmp_path)

    # Forget the second memory (in session sA): 4 groups -> 3 groups.
    ok = c_store.change_status(lane_key=LANE, item_id=ids[1], action="forget")
    assert ok is True

    after = explain(store, label_id)["label"]
    # HIGH required >=4 support events; with 3 it must fall back to MEDIUM.
    assert after["grade"] == "medium" and after["state"] == "supported"
    # Orphaned evidence row pointing at the forgotten memory is pruned.
    assert _evidence_count(store, label_id) == 3
    with store.connect() as db:
        remaining = [r["evidence_ref"] for r in db.execute(
            "SELECT evidence_ref FROM evidence WHERE label_id=?", (label_id,))]
    assert f"continuity:{ids[1]}" not in remaining


def test_forget_all_support_collapses_to_tentative(tmp_path):
    label_id, ids, store = _build_high_label(tmp_path)
    c_store = StructuredMemoryStore(tmp_path)
    for mid in ids:
        assert c_store.change_status(lane_key=LANE, item_id=mid, action="forget")

    after = explain(store, label_id)["label"]
    assert after["grade"] == "low" and after["state"] == "tentative"
    assert _evidence_count(store, label_id) == 0


def test_detach_evidence_api_regrades_label(tmp_path, monkeypatch):
    label_id, ids, store = _build_high_label(tmp_path)
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home",
                        lambda: tmp_path)
    app = FastAPI()
    app.include_router(understanding_router)
    client = TestClient(app)

    ref = f"continuity:{ids[1]}"
    resp = client.request("DELETE",
                          f"/api/understanding/labels/{label_id}/evidence",
                          params={"ref": ref})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["removed"] == 1
    assert body["recomputed"]["changed"] is True

    after = explain(store, label_id)["label"]
    assert after["grade"] == "medium"
    assert _evidence_count(store, label_id) == 3


def test_detach_counter_reverts_disputed_to_supported(tmp_path, monkeypatch):
    label_id, ids, store = _build_high_label(tmp_path)
    # Add a 5th active episode as counter evidence.
    counter_id = _record_episodes(tmp_path, 1)[0]
    counter_ref = f"continuity:{counter_id}"
    apply_proposal(
        store, owner=OWNER, lane=LANE, namespace=NS,
        proposal=_proposal([], [counter_ref]),
        evidence_meta={counter_ref: ("gc", "sX", "rev", _iso(1))},
        continuity_db_path=tmp_path / "continuity.db",
    )
    disputed = explain(store, label_id)["label"]
    assert disputed["state"] == "disputed" and disputed["grade"] == "low"

    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home",
                        lambda: tmp_path)
    app = FastAPI()
    app.include_router(understanding_router)
    client = TestClient(app)
    resp = client.request("DELETE",
                          f"/api/understanding/labels/{label_id}/evidence",
                          params={"ref": counter_ref})
    assert resp.status_code == 200, resp.text
    assert resp.json()["recomputed"]["changed"] is True

    back = explain(store, label_id)["label"]
    assert back["state"] == "supported" and back["grade"] == "high"


def test_recompute_never_revives_user_suppressed_label(tmp_path):
    label_id, ids, store = _build_high_label(tmp_path)
    suppress(store, label_id)  # state -> user_suppressed, body -> ""
    before = explain(store, label_id)["label"]
    assert before["state"] == "user_suppressed" and before["body"] == ""
    assert _evidence_count(store, label_id) == 4  # suppress() keeps evidence

    # Forgetting the source must NOT revive the label or restore its body.
    c_store = StructuredMemoryStore(tmp_path)
    c_store.change_status(lane_key=LANE, item_id=ids[0], action="forget")
    after = explain(store, label_id)["label"]
    assert after["state"] == "user_suppressed" and after["body"] == ""

    # Direct recompute explicitly reports the skip reason.
    result = recompute_label(store, label_id,
                             continuity_db_path=tmp_path / "continuity.db")
    assert result["changed"] is False
    assert result["reason"] == "user_suppressed"


def test_apply_proposal_prunes_orphans_and_does_not_inflate(tmp_path):
    label_id, ids, store = _build_high_label(tmp_path)
    # Simulate a source withdrawn outside the hooks (e.g. raw archival) so an
    # orphan evidence row remains. The next proposal must not keep HIGH.
    with sqlite3.connect(tmp_path / "continuity.db") as db:
        db.execute("UPDATE structured_memories SET status='archived' WHERE id=?",
                   (ids[0],))
    # One fresh valid support memory + proposal for the same label. Place it 10
    # days ago so the remaining valid set keeps span >= 7 and stays HIGH.
    new_id = _record_episodes(tmp_path, 1)[0]
    new_ref = f"continuity:{new_id}"
    apply_proposal(
        store, owner=OWNER, lane=LANE, namespace=NS,
        proposal=_proposal([new_ref]),
        evidence_meta={new_ref: ("g9", "s9", "rev", _iso(10))},
        continuity_db_path=tmp_path / "continuity.db",
    )
    after = explain(store, label_id)["label"]
    # Orphan (archived ids[0]) pruned; valid evidence = ids[1..3] + new = 4
    # groups / 4 sessions / span 10d -> still HIGH, but the archived row gone.
    assert _evidence_count(store, label_id) == 4
    with store.connect() as db:
        refs = [r["evidence_ref"] for r in db.execute(
            "SELECT evidence_ref FROM evidence WHERE label_id=?", (label_id,))]
    assert f"continuity:{ids[0]}" not in refs
    assert new_ref in refs
    assert after["grade"] == "high"


def test_recompute_labels_for_memory_touches_every_citing_label(tmp_path):
    # Two labels both cite memory M.
    ids = _record_episodes(tmp_path, 2)
    m = ids[0]
    store = UnderstandingStore(tmp_path / "understanding_v2.db")
    store.initialize()
    common = {f"continuity:{m}": ("g0", "sA", "rev", _iso(5))}
    lid_a = apply_proposal(
        store, owner=OWNER, lane=LANE, namespace=NS,
        proposal=Proposal("propose", "interest_preference", "learning",
                          "mechanism_first", "A", (f"continuity:{m}",), ()),
        evidence_meta=common, continuity_db_path=tmp_path / "continuity.db")
    lid_b = apply_proposal(
        store, owner=OWNER, lane=LANE, namespace=NS,
        proposal=Proposal("propose", "communication_style", "learning",
                          "direct", "B", (f"continuity:{m}",), ()),
        evidence_meta=common, continuity_db_path=tmp_path / "continuity.db")

    results = recompute_labels_for_memory(
        store, continuity_db_path=tmp_path / "continuity.db", memory_id=m)
    # No forget happened yet -> both already consistent, nothing changes.
    assert all(not r["changed"] for r in results)

    StructuredMemoryStore(tmp_path).change_status(
        lane_key=LANE, item_id=m, action="forget")
    # The targeted hook already recomputed; reconcile confirms a clean sweep.
    sweep = reconcile_store(store, continuity_db_path=tmp_path / "continuity.db")
    assert sweep["changed"] == 0
    for lid in (lid_a, lid_b):
        assert explain(store, lid)["label"]["state"] == "tentative"
        assert _evidence_count(store, lid) == 0


def test_concurrent_source_changes_do_not_corrupt_label(tmp_path):
    label_id, ids, store = _build_high_label(tmp_path)
    c_store = StructuredMemoryStore(tmp_path)
    errors: list[BaseException] = []

    def forget_one(mid):
        try:
            c_store.change_status(lane_key=LANE, item_id=mid, action="forget")
        except BaseException as exc:  # noqa: BLE001 - surface any failure
            errors.append(exc)

    t1 = threading.Thread(target=forget_one, args=(ids[0],))
    t2 = threading.Thread(target=forget_one, args=(ids[3],))
    t1.start(); t2.start(); t1.join(); t2.join()
    assert not errors, [repr(e) for e in errors]

    # Final state is consistent: 2 support events remain -> MEDIUM/SUPPORTED,
    # no leftover orphan rows, revision is a sane monotonic integer.
    after = explain(store, label_id)
    label = after["label"]
    assert label["grade"] == "medium" and label["state"] == "supported"
    assert _evidence_count(store, label_id) == 2
    assert isinstance(label["revision"], int) and label["revision"] >= 1
    with store.connect() as db:
        versions = db.execute(
            "SELECT COUNT(*) FROM label_versions WHERE label_id=?", (label_id,),
        ).fetchone()[0]
    # Each successful re-evaluation records at most one version snapshot.
    assert versions <= 2


def test_label_detail_exposes_versions_and_masks_body_after_forget(tmp_path, monkeypatch):
    label_id, ids, store = _build_high_label(tmp_path)
    monkeypatch.setattr("honeyos.core.constants.get_honeyos_home",
                        lambda: tmp_path)
    app = FastAPI()
    app.include_router(understanding_router)
    client = TestClient(app)

    # Detach one relation so a re-evaluation version snapshot is recorded.
    client.request("DELETE", f"/api/understanding/labels/{label_id}/evidence",
                   params={"ref": f"continuity:{ids[1]}"})

    detail = client.get(f"/api/understanding/labels/{label_id}").json()
    assert detail["versions"], "label detail must expose version history"
    first = detail["versions"][0]
    assert first["body"]  # body visible while label is active

    # After the user forgets the label, historical bodies must be masked.
    client.post(f"/api/understanding/labels/{label_id}/suppress")
    hidden = client.get(f"/api/understanding/labels/{label_id}").json()
    assert hidden["suppressed"] is True
    assert hidden["text"] == ""
    assert all(v["body"] == "" for v in hidden["versions"])
