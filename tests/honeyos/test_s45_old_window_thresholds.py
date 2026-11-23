"""S4.5 Task C: old-window 6/40 threshold retention audit.

These tests prove that the existing MemoryDistiller never *silently loses*
already-eligible transcript material around the ``min_tail_messages`` (6) and
``max_batch_messages`` (40) boundaries, and that sub-threshold tails stay in a
durable pending state rather than being dropped.  No production behaviour is
changed by these tests; they characterise the frozen contract.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.companion.distillation import DistillationSettings, MemoryDistiller

NOW = datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc)
LANE = "agent:main:api_server:dm:local-owner"


def _messages(count: int, *, start: int = 1) -> list[dict]:
    return [
        {
            "_row_id": start + index,
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"message-{start + index}",
        }
        for index in range(count)
    ]


class _RecordingExtractor:
    """Capture the exact row_ids each distillation batch actually saw."""

    def __init__(self) -> None:
        self.batches: list[list[int]] = []

    async def __call__(self, job, _active, _runtime):
        self.batches.append([message["_row_id"] for message in job.messages])
        return json.dumps({"operations": []})

    @property
    def seen(self) -> list[int]:
        return [row for batch in self.batches for row in batch]


def _cursor(tmp_path, session_id: str) -> int:
    distiller = MemoryDistiller(tmp_path)
    with distiller._connect() as connection:
        row = connection.execute(
            "SELECT last_source_row_id FROM distillation_state "
            "WHERE lane_key = ? AND session_id = ?",
            (LANE, session_id),
        ).fetchone()
    return int(row[0]) if row is not None else 0


@pytest.mark.asyncio
async def test_one_and_five_message_tails_are_deferred_not_lost(tmp_path):
    extractor = _RecordingExtractor()
    distiller = MemoryDistiller(
        tmp_path,
        settings=DistillationSettings(min_tail_messages=6),
        extractor=extractor,
    )

    for size in (1, 5):
        result = await distiller.distill_if_due(
            lane_key=LANE,
            session_id=f"tail-{size}",
            messages=_messages(size),
            reason="new",
            now=NOW,
        )
        assert result is None
        assert _cursor(tmp_path, f"tail-{size}") == 0
    assert extractor.batches == []

    # The same window, once it reaches the 6-unit floor, is processed and the
    # earlier deferred messages are included rather than skipped.
    grown = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="tail-5",
        messages=_messages(6),
        reason="new",
        now=NOW,
    )
    assert grown is not None and grown.status == "completed"
    assert extractor.batches[-1] == [1, 2, 3, 4, 5, 6]
    assert _cursor(tmp_path, "tail-5") == 6


@pytest.mark.asyncio
async def test_exactly_six_is_processed_in_one_batch(tmp_path):
    extractor = _RecordingExtractor()
    distiller = MemoryDistiller(
        tmp_path,
        settings=DistillationSettings(min_tail_messages=6),
        extractor=extractor,
    )
    result = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="six",
        messages=_messages(6),
        reason="session_switch",
        now=NOW,
    )
    assert result is not None and result.status == "completed"
    assert extractor.batches == [[1, 2, 3, 4, 5, 6]]


@pytest.mark.asyncio
async def test_periodic_twenty_trigger_semantics_unchanged(tmp_path):
    extractor = _RecordingExtractor()
    distiller = MemoryDistiller(
        tmp_path,
        settings=DistillationSettings(trigger_messages=20),
        extractor=extractor,
    )
    under = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="periodic",
        messages=_messages(19),
        reason="periodic",
        now=NOW,
    )
    assert under is None
    assert extractor.batches == []

    at_threshold = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="periodic",
        messages=_messages(20),
        reason="periodic",
        now=NOW,
    )
    assert at_threshold is not None and at_threshold.status == "completed"
    assert len(extractor.batches) == 1
    assert extractor.batches[0] == list(range(1, 21))


@pytest.mark.asyncio
async def test_forty_messages_fit_session_switch_batch(tmp_path):
    extractor = _RecordingExtractor()
    distiller = MemoryDistiller(
        tmp_path,
        settings=DistillationSettings(min_tail_messages=6, max_batch_messages=40),
        extractor=extractor,
    )
    result = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="forty",
        messages=_messages(40),
        reason="session_switch",
        now=NOW,
    )
    assert result is not None and result.status == "completed"
    assert extractor.batches == [list(range(1, 41))]
    assert _cursor(tmp_path, "forty") == 40


@pytest.mark.asyncio
async def test_forty_one_messages_remainder_processed_later(tmp_path):
    extractor = _RecordingExtractor()
    distiller = MemoryDistiller(
        tmp_path,
        settings=DistillationSettings(min_tail_messages=6, max_batch_messages=40),
        extractor=extractor,
    )
    first = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="fortyone",
        messages=_messages(41),
        reason="session_switch",
        now=NOW,
    )
    assert first is not None and first.status == "completed"
    assert extractor.batches == [list(range(1, 41))]
    # 1 unprocessed message remains pending (row 41); the cursor must be exactly
    # at the last processed row, never past it.
    assert _cursor(tmp_path, "fortyone") == 40

    # Growing the window past the 6-unit floor lets the remainder be processed.
    second = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="fortyone",
        messages=_messages(46),
        reason="session_switch",
        now=NOW,
    )
    assert second is not None and second.status == "completed"
    assert extractor.batches[-1] == [41, 42, 43, 44, 45, 46]
    assert _cursor(tmp_path, "fortyone") == 46
    # Nothing was skipped and nothing was processed twice.
    assert sorted(extractor.seen) == list(range(1, 47))


@pytest.mark.asyncio
async def test_eighty_messages_processed_across_repeated_switches(tmp_path):
    extractor = _RecordingExtractor()
    distiller = MemoryDistiller(
        tmp_path,
        settings=DistillationSettings(min_tail_messages=6, max_batch_messages=40),
        extractor=extractor,
    )
    for _ in range(2):
        result = await distiller.distill_if_due(
            lane_key=LANE,
            session_id="eighty",
            messages=_messages(80),
            reason="session_switch",
            now=NOW,
        )
        assert result is not None and result.status == "completed"

    assert extractor.batches == [list(range(1, 41)), list(range(41, 81))]
    assert _cursor(tmp_path, "eighty") == 80
    assert sorted(extractor.seen) == list(range(1, 81))


@pytest.mark.asyncio
async def test_daily_cap_defers_without_advancing_cursor(tmp_path):
    extractor = _RecordingExtractor()
    distiller = MemoryDistiller(
        tmp_path,
        settings=DistillationSettings(
            trigger_messages=1, max_daily_runs=1, min_tail_messages=1
        ),
        extractor=extractor,
    )
    first = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="cap-a",
        messages=_messages(1),
        reason="periodic",
        now=NOW,
    )
    blocked = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="cap-b",
        messages=_messages(1),
        reason="periodic",
        now=NOW,
    )
    assert first is not None and first.status == "completed"
    assert blocked is None
    assert _cursor(tmp_path, "cap-b") == 0

    # The deferred session is still fully available to a later legal run.
    later = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="cap-b",
        messages=_messages(1),
        reason="periodic",
        now=NOW + timedelta(days=1),
    )
    assert later is not None and later.status == "completed"
    assert _cursor(tmp_path, "cap-b") == 1


@pytest.mark.asyncio
async def test_retry_after_failure_does_not_duplicate_memories(tmp_path):
    attempts = {"count": 0}

    async def extractor(job, _active, _runtime):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient model failure")
        return json.dumps(
            {
                "operations": [
                    {
                        "action": "record",
                        "kind": "open_loop",
                        "content": "继续验证旧窗口补偿",
                        "evidence": "user_stated",
                        "evidence_message_ids": [1],
                    }
                ]
            },
            ensure_ascii=False,
        )

    distiller = MemoryDistiller(tmp_path, extractor=extractor)
    failed = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="retry",
        messages=_messages(20),
        reason="periodic",
        now=NOW,
    )
    assert failed is not None and failed.status == "failed"
    assert _cursor(tmp_path, "retry") == 0

    recovered = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="retry",
        messages=_messages(20),
        reason="periodic",
        now=NOW,
    )
    assert recovered is not None and recovered.status == "completed"
    assert _cursor(tmp_path, "retry") == 20
    items = StructuredMemoryStore(tmp_path).list_active(lane_key=LANE, now=NOW)
    assert len(items) == 1
    assert items[0].content == "继续验证旧窗口补偿"


@pytest.mark.asyncio
async def test_forgotten_memory_is_not_revived_by_replay(tmp_path):
    async def extractor(_job, _active, _runtime):
        return json.dumps(
            {
                "operations": [
                    {
                        "action": "record",
                        "kind": "open_loop",
                        "content": "提醒我周五交报告",
                        "evidence": "user_stated",
                        "evidence_message_ids": [1],
                    }
                ]
            },
            ensure_ascii=False,
        )

    distiller = MemoryDistiller(tmp_path, extractor=extractor)
    first = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="forget",
        messages=_messages(20),
        reason="periodic",
        now=NOW,
    )
    assert first is not None and first.status == "completed"
    store = StructuredMemoryStore(tmp_path)
    item = store.list_active(lane_key=LANE, now=NOW)[0]
    assert store.change_status(
        lane_key=LANE, item_id=item.id, action="forget", now=NOW
    )

    # Same source range is idempotent: no re-run, so nothing is revived.
    replay = await distiller.distill_if_due(
        lane_key=LANE,
        session_id="forget",
        messages=_messages(20),
        reason="periodic",
        now=NOW,
    )
    assert replay is None
    assert store.list_active(lane_key=LANE, now=NOW) == ()
