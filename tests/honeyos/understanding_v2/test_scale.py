import time
from datetime import datetime, timezone

from honeyos.understanding.u2_context import compose_memory_context
from honeyos.understanding.u2_contracts import ContextSegment
from honeyos.understanding.u2_store import UnderstandingStore


def test_composer_work_is_bounded_by_supplied_candidates():
    # Retrieval owns the 36-header bound; the composer must remain linear in
    # that already-bounded handoff and must not discover or scan a store.
    for database_size in (100, 1_000, 10_000):
        candidates = tuple(
            ContextSegment(f"s{i}", f"source:{i}", "1", "memory", "user",
                           f"text {i}", 3, 1)
            for i in range(36)
        )
        started = time.perf_counter()
        result = compose_memory_context(candidates, total_budget=30,
                                        current_policy_epoch=1)
        elapsed = time.perf_counter() - started
        assert len(result.segment_ids) == 10
        assert result.truncated
        assert elapsed < .25, database_size


def test_ten_thousand_label_page_uses_bounded_indexed_query(tmp_path):
    store = UnderstandingStore(tmp_path / "u2.db")
    store.initialize()
    now = datetime.now(timezone.utc).isoformat()
    with store.connect() as db:
        db.executemany("""INSERT INTO labels
            (id,owner,lane,namespace,category,scope_key,canonical_key,body,state,grade,
             revision,policy_epoch,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ((f"l{i:05d}", "local-owner", "lane", "companion", "learning_work_style",
              "learning", f"key-{i}", f"body-{i}", "tentative", "low", 1, 0, now, now)
             for i in range(10_000)))
        plan = db.execute("""EXPLAIN QUERY PLAN SELECT * FROM labels
            WHERE owner=? AND lane=? AND namespace=?
            ORDER BY updated_at DESC,id LIMIT ? OFFSET ?""",
            ("local-owner", "lane", "companion", 50, 9_950)).fetchall()
    started = time.perf_counter()
    rows, total = store.page_labels("local-owner", "lane", "companion", limit=50, offset=9_950)
    elapsed = time.perf_counter() - started
    assert total == 10_000 and len(rows) == 50
    assert any("ix_labels_scope_updated" in str(tuple(row)) for row in plan)
    assert elapsed < 1.0
