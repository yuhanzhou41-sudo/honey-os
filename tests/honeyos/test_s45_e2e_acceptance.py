"""S4.5 Task A: isolated end-to-end acceptance for the 8 required scenarios.

Runs the real chain in a throwaway HoneyOS home:

    MemoryDistiller._prepare -> fake extractor -> continuity.db writes ->
    (optional) understanding parse -> GatewayRunner._honeyos_u2_post_completed
    -> apply_proposal -> understanding_v2.db -> graph API handlers.

No production ``~/.honeyos`` is touched, no network/model call is made, and
``HONEYOS_HOME`` / ``HONEYOS_RUNTIME_ID`` are isolated per test.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.companion.distillation import (
    DistillationSettings,
    MemoryDistiller,
    load_distillation_settings,
)
from honeyos.companion.emotional_imprint import EmotionalImprintStore
from honeyos.gateway.run import GatewayRunner
from honeyos.memory.repository import CognitiveMemoryRepository
from honeyos.understanding.u2_contracts import Proposal
from honeyos.understanding.u2_maintenance import apply_proposal
from honeyos.understanding.u2_store import UnderstandingStore

NOW = datetime(2026, 8, 7, 8, 0, tzinfo=timezone.utc)
LANE = "agent:main:api_server:dm:local-owner"
OWNER = "local-owner"
TOPIC = "项目规划复盘"


def _write_config(home: Path) -> None:
    (home / "config.yaml").write_text(
        "memory:\n"
        "  distillation:\n"
        "    enabled: true\n"
        "    understanding:\n"
        "      enabled: true\n"
        "      namespace: general\n",
        encoding="utf-8",
    )


@pytest.fixture
def honey_home(tmp_path, monkeypatch):
    home = tmp_path / "honey_home"
    home.mkdir()
    _write_config(home)
    monkeypatch.setenv("HONEYOS_HOME", str(home))
    monkeypatch.setenv("HONEYOS_RUNTIME_ID", "honeyos-companion-s45test")
    return home


def _convo(count: int, *, start: int = 1, topic: str = TOPIC) -> list[dict]:
    return [
        {
            "_row_id": start + index,
            "role": "user" if index % 2 == 0 else "assistant",
            "content": f"{topic} 第{start + index}条：我们一起把执行步骤和细节排清楚。",
        }
        for index in range(count)
    ]


class _Extractor:
    def __init__(self, payload_fn):
        self.payload_fn = payload_fn
        self.calls = 0

    async def __call__(self, job, _active, _runtime):
        self.calls += 1
        return json.dumps(self.payload_fn(job), ensure_ascii=False)


def _default_payload(job):
    ids = [message["_row_id"] for message in job.messages]
    return {
        "chapter": {
            "title": "一起理清项目规划的步骤",
            "summary": "我们一起讨论了项目规划的推进细节，我记得你希望先排清步骤再执行。",
            "evidence_message_ids": ids[:2],
        },
        "operations": [
            {
                "action": "record",
                "kind": "episode",
                "content": f"{TOPIC}：我们一起梳理了里程碑与执行顺序。",
                "evidence": "conversation_event",
                "evidence_message_ids": [ids[0], ids[1]],
            },
            {
                "action": "record",
                "kind": "commitment",
                "content": "我答应你下次继续跟进项目规划。",
                "evidence": "assistant_committed",
                "evidence_message_ids": [ids[-1]],
            },
        ],
        "understandings": [
            {
                "operation": "propose",
                "category_id": "behavior_pattern",
                "scope_key": "workflow",
                "canonical_key": "prefers_planning_first",
                "text": "你倾向在执行前先做规划。",
                "operation_indices": [0],
            }
        ],
    }


def _u2_hook(settings):
    """Bind the REAL GatewayRunner U2 same-batch method without __init__."""
    shim = object.__new__(GatewayRunner)

    async def hook(*, job, result, main_runtime):
        await GatewayRunner._honeyos_u2_post_completed(
            shim,
            job=job,
            result=result,
            main_runtime=main_runtime,
            settings=settings,
        )

    return hook


async def _distill(home, *, session, count=20, start=1, payload_fn=_default_payload, reason="periodic"):
    settings = load_distillation_settings(home)
    extractor = _Extractor(payload_fn)
    distiller = MemoryDistiller(
        home,
        settings=settings,
        extractor=extractor,
        post_completed_hook=_u2_hook(settings.understanding),
    )
    result = await distiller.distill_if_due(
        lane_key=LANE,
        session_id=session,
        messages=_convo(count, start=start),
        reason=reason,
        now=NOW,
    )
    return result, extractor, settings


def _labels(home):
    store = UnderstandingStore(home / "understanding_v2.db")
    rows, total = store.page_labels(OWNER, LANE, "general")
    return store, rows, total


def _memory_status(home: Path, memory_id: str) -> str:
    with sqlite3.connect(home / "continuity.db") as db:
        row = db.execute(
            "SELECT status FROM structured_memories WHERE id=?", (memory_id,)
        ).fetchone()
    return str(row[0]) if row else "missing"


def _seed_imprint(home: Path, memory_id: str, status: str, axis: str, label: str):
    conn = sqlite3.connect(home / "continuity.db")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS structured_memory_emotional_imprints(
            memory_id TEXT PRIMARY KEY, lane_key TEXT NOT NULL, kind TEXT NOT NULL,
            status TEXT NOT NULL, dominant_axis TEXT, dominant_label TEXT,
            basis_axes_json TEXT NOT NULL DEFAULT '[]',
            basis_turn_ids_json TEXT NOT NULL DEFAULT '[]',
            formed_at TEXT, recorded_at TEXT NOT NULL,
            distillation_run_id TEXT, evidence_summary TEXT NOT NULL)"""
    )
    conn.execute(
        "INSERT OR REPLACE INTO structured_memory_emotional_imprints "
        "(memory_id,lane_key,kind,status,dominant_axis,dominant_label,"
        "basis_axes_json,basis_turn_ids_json,formed_at,recorded_at,evidence_summary)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (memory_id, LANE, "episode", status, axis, label, "[]", "[]",
         NOW.isoformat(), NOW.isoformat(), "test"),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# Scenario 1: full automatic organization (distiller + U2 same batch + API)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_1_full_automatic_organization(honey_home):
    from honeyos.runtime.web_routers.understanding import get_understanding_graph

    result, extractor, settings = await _distill(honey_home, session="s1")

    assert result is not None and result.status == "completed"
    assert extractor.calls == 1  # exactly one model request for the batch
    assert result.applied >= 2 and result.rejected == 0
    assert 0 in result.applied_indices  # op index -> real continuity memory id

    memories = StructuredMemoryStore(honey_home).list_active(lane_key=LANE, now=NOW)
    active_ids = {item.id for item in memories}
    assert result.applied_indices[0] in active_ids

    # U2 written through apply_proposal in the SAME batch (no extra LLM call).
    _, labels, total = _labels(honey_home)
    assert total == 1
    assert labels[0]["canonical_key"] == "prefers_planning_first"
    assert labels[0]["body"] == "你倾向在执行前先做规划。"

    # Gateway graph API reads the real SQLite store.
    graph = get_understanding_graph(lane="", namespace="", limit=50, offset=0)
    assert graph["total"] == 1
    evidence = graph["labels"][0]["evidence"]
    assert evidence and evidence[0]["relation"] == "support"
    assert evidence[0]["ref"] == f"continuity:{result.applied_indices[0]}"
    assert evidence[0]["memory"]["content"]


# --------------------------------------------------------------------------- #
# Scenario 1b: real Gateway hook composition (emotion hook -> async U2)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_1b_emotion_hook_forwards_to_async_u2(honey_home):
    """Regression guard: the emotion-imprint hook must forward to the async
    U2 same-batch producer. A dropped coroutine would silently skip U2."""
    from honeyos.companion.emotional_imprint import emotion_imprint_hook_factory

    settings = load_distillation_settings(honey_home)
    extractor = _Extractor(_default_payload)
    shim = object.__new__(GatewayRunner)

    async def u2_downstream(*, job, result, main_runtime):
        await GatewayRunner._honeyos_u2_post_completed(
            shim, job=job, result=result, main_runtime=main_runtime,
            settings=settings.understanding,
        )

    holder = [u2_downstream]
    distiller = MemoryDistiller(
        honey_home,
        settings=settings,
        extractor=extractor,
        post_completed_hook=emotion_imprint_hook_factory(
            home=honey_home, downstream_holder=holder
        ),
    )
    result = await distiller.distill_if_due(
        lane_key=LANE, session_id="s1b", messages=_convo(20),
        reason="periodic", now=NOW,
    )
    assert result is not None and result.status == "completed"
    _, labels, total = _labels(honey_home)
    assert total == 1  # proves the async U2 producer actually ran via the hook


# --------------------------------------------------------------------------- #
# Scenario 2: a second shared experience supports an existing understanding
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_2_new_evidence_does_not_duplicate_label(honey_home):
    first, ext1, _ = await _distill(honey_home, session="s2a")
    assert first is not None and first.status == "completed" and ext1.calls == 1

    second, ext2, _ = await _distill(honey_home, session="s2b", start=101)
    assert second is not None and second.status == "completed" and ext2.calls == 1

    store, labels, total = _labels(honey_home)
    assert total == 1  # no duplicate synonym label
    label_id = labels[0]["id"]
    with store.connect() as db:
        rows = db.execute(
            "SELECT evidence_ref, relation FROM evidence WHERE label_id=?",
            (label_id,),
        ).fetchall()
        revision = db.execute(
            "SELECT revision FROM labels WHERE id=?", (label_id,)
        ).fetchone()[0]
    refs = sorted(row["evidence_ref"] for row in rows)
    assert len(rows) == 2 and all(row["relation"] == "support" for row in rows)
    assert refs == sorted([
        f"continuity:{first.applied_indices[0]}",
        f"continuity:{second.applied_indices[0]}",
    ])
    assert revision == 2
    # Replaying the exact same batch does not add evidence or call the model.
    replay, ext3, _ = await _distill(honey_home, session="s2b", start=101)
    assert replay is None and ext3.calls == 0


# --------------------------------------------------------------------------- #
# Scenario 3: one memory linked to two different labels (many-to-many)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_3_one_memory_two_labels(honey_home):
    def payload(job):
        base = _default_payload(job)
        base["operations"] = base["operations"][:1]  # only the episode
        base["understandings"] = [
            {
                "operation": "propose",
                "category_id": "behavior_pattern",
                "scope_key": "workflow",
                "canonical_key": "prefers_planning_first",
                "text": "你倾向在执行前先做规划。",
                "operation_indices": [0],
            },
            {
                "operation": "propose",
                "category_id": "value_tendency",
                "scope_key": "workflow",
                "canonical_key": "values_careful_review",
                "text": "你重视复盘与核对。",
                "operation_indices": [0],
            },
        ]
        return base

    result, extractor, _ = await _distill(honey_home, session="s3", payload_fn=payload)
    assert result is not None and result.status == "completed" and extractor.calls == 1

    memory_id = result.applied_indices[0]
    memories = StructuredMemoryStore(honey_home).list_active(lane_key=LANE, now=NOW)
    matching = [item for item in memories if item.id == memory_id]
    assert len(matching) == 1  # the native memory is stored exactly once

    store, labels, total = _labels(honey_home)
    assert total == 2
    ref = f"continuity:{memory_id}"
    with store.connect() as db:
        by_label = {
            row["label_id"]: row["evidence_ref"]
            for row in db.execute(
                "SELECT label_id, evidence_ref FROM evidence ORDER BY label_id"
            ).fetchall()
        }
    assert set(by_label.values()) == {ref}
    assert len(by_label) == 2

    from honeyos.runtime.web_routers.understanding import get_understanding_label

    for label in labels:
        detail = get_understanding_label(label["id"])
        assert [e["ref"] for e in detail["evidence"]] == [ref]


# --------------------------------------------------------------------------- #
# Scenario 4: user manual forget is never revived
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_4_user_forget_blocks_recall_and_revival(honey_home):
    from honeyos.runtime.web_routers.understanding import get_understanding_label

    result, _, _ = await _distill(honey_home, session="s4")
    memory_id = result.applied_indices[0]
    store = StructuredMemoryStore(honey_home)
    _, labels, _ = _labels(honey_home)
    label_id = labels[0]["id"]
    label_state_before = labels[0]["state"]

    assert store.change_status(lane_key=LANE, item_id=memory_id, action="forget", now=NOW)
    assert _memory_status(honey_home, memory_id) == "forgotten"

    # Graph API no longer returns the forgotten memory body as evidence.
    detail = get_understanding_label(label_id)
    assert all(e["memory"] is None for e in detail["evidence"])
    assert detail["evidence"] == []
    # The label's own state is untouched: memory-forget != label-forget.
    assert detail["state"] == label_state_before

    # Recall never injects the forgotten memory, even with hot physiology.
    monkeypatch_live = {"epinephrine": 0.95}
    import honeyos.companion.physiology_shadow as phys

    original = phys.live_signals
    phys.live_signals = lambda home, now=None: monkeypatch_live
    try:
        note = store.context_for_lane(lane_key=LANE, now=NOW, query=TOPIC)
    finally:
        phys.live_signals = original
    assert memory_id not in (note or "")

    # A late/old U2 write cannot cite the forgotten memory.
    meta = GatewayRunner._honeyos_u2_evidence_meta(honey_home, {0: memory_id}, LANE)
    assert meta == {}
    proposal = Proposal(
        operation="support", category_id="behavior_pattern", scope_key="workflow",
        canonical_key="prefers_planning_first", text="你倾向在执行前先做规划。",
        support_refs=(f"continuity:{memory_id}",),
    )
    with pytest.raises(ValueError):
        apply_proposal(
            UnderstandingStore(honey_home / "understanding_v2.db"),
            owner=OWNER, lane=LANE, namespace="general", proposal=proposal,
            evidence_meta=meta,
        )

    # Background replay of the same old batch does not run again, and a direct
    # background record of the same content is refused for a forgotten item.
    replay, extractor, _ = await _distill(honey_home, session="s4")
    assert replay is None and extractor.calls == 0
    revived = store.record(
        lane_key=LANE, kind="episode",
        content=f"{TOPIC}：我们一起梳理了里程碑与执行顺序。",
        evidence="conversation_event", source_session_id="s4",
        source_message_ids=(1,), created_by="background", now=NOW,
    )
    assert revived is None


# --------------------------------------------------------------------------- #
# Scenario 5: open_loop completion via the existing management tool
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_5_open_loop_completion(honey_home, monkeypatch):
    from honeyos.study.repository import StudyRepository
    from honeyos.tools import companion_memory_tool as tool_module

    store = StructuredMemoryStore(honey_home)
    item = store.record(
        lane_key=LANE, kind="open_loop",
        content=f"{TOPIC} 还有一项没有继续聊完。",
        evidence="user_stated", source_session_id="s5",
        source_message_ids=(1,), created_by="foreground", now=NOW,
    )
    assert item is not None
    assert any(i.id == item.id for i in store.list_active(lane_key=LANE, now=NOW))
    assert item.id in (store.context_for_lane(lane_key=LANE, now=NOW, query=TOPIC) or "")

    plans_before = len(StudyRepository(honey_home).list_plans())
    monkeypatch.setattr(
        tool_module, "get_current_session_key", lambda default="": LANE
    )
    resolved = json.loads(
        tool_module.companion_memory_tool(action="resolve", item_id=item.id)
    )
    assert resolved["success"] is True

    # Completed item disappears from the original pending surface and recall.
    assert all(i.id != item.id for i in store.list_active(lane_key=LANE, now=NOW))
    assert item.id not in (store.context_for_lane(lane_key=LANE, now=NOW, query=TOPIC) or "")
    assert len(StudyRepository(honey_home).list_plans()) == plans_before
    # open_loop is not valid U2 evidence.
    assert GatewayRunner._honeyos_u2_evidence_meta(honey_home, {0: item.id}, LANE) == {}


# --------------------------------------------------------------------------- #
# Scenario 6: bounded physiology recall + S4 historical imprint
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_6_physiology_and_imprint(honey_home, monkeypatch):
    store = StructuredMemoryStore(honey_home)
    older_known = store.record(
        lane_key=LANE, kind="episode",
        content=f"{TOPIC}：我们一起梳理了里程碑。", evidence="conversation_event",
        source_session_id="s6", source_message_ids=(1,), created_by="background",
        now=NOW - timedelta(days=2),
    )
    newer_plain = store.record(
        lane_key=LANE, kind="commitment",
        content=f"{TOPIC}：我答应你继续跟进。", evidence="assistant_committed",
        source_session_id="s6", source_message_ids=(2,), created_by="background",
        now=NOW - timedelta(days=1),
    )
    forgotten = store.record(
        lane_key=LANE, kind="episode",
        content=f"{TOPIC}：我们一起列了清单。", evidence="conversation_event",
        source_session_id="s6", source_message_ids=(3,), created_by="background",
        now=NOW - timedelta(days=1),
    )
    resolved_loop = store.record(
        lane_key=LANE, kind="open_loop",
        content=f"{TOPIC} 还没聊完的继续事项。", evidence="user_stated",
        source_session_id="s6", source_message_ids=(4,), created_by="foreground",
        now=NOW - timedelta(days=1),
    )
    off_topic = store.record(
        lane_key=LANE, kind="episode",
        content="周末我们去山里看了很震撼的日出，情绪非常强烈。",
        evidence="conversation_event", source_session_id="s6",
        source_message_ids=(5,), created_by="background", now=NOW - timedelta(days=1),
    )
    unknown_imprint = store.record(
        lane_key=LANE, kind="episode",
        content="项目规划复盘里还有一段关于预算的对话。",
        evidence="conversation_event", source_session_id="s6",
        source_message_ids=(6,), created_by="background", now=NOW - timedelta(days=3),
    )
    assert all((older_known, newer_plain, forgotten, resolved_loop, off_topic, unknown_imprint))

    _seed_imprint(honey_home, older_known.id, "known", "warmth", "温暖")
    _seed_imprint(honey_home, unknown_imprint.id, "unknown", None, None)
    store.change_status(lane_key=LANE, item_id=forgotten.id, action="forget", now=NOW)
    store.change_status(lane_key=LANE, item_id=resolved_loop.id, action="resolve", now=NOW)

    import honeyos.companion.physiology_shadow as phys

    monkeypatch.setattr(phys, "live_signals", lambda home, now=None: {"epinephrine": 0.95})

    note = store.context_for_lane(lane_key=LANE, now=NOW, query=TOPIC) or ""
    assert older_known.id in note
    # known imprint lifts the older memory ahead of the newer plain one.
    assert note.index(older_known.id) < note.index(newer_plain.id)
    assert "历史情绪印记" in note and "当时" in note
    # forgotten / resolved memories never surface.
    assert forgotten.id not in note
    assert resolved_loop.id not in note
    # off-topic strong-emotion memory never crosses the relevance gate.
    assert "山里" not in note
    # unknown imprint is present but never presented as a known feeling.
    assert unknown_imprint.id in note
    assert f"[{unknown_imprint.id}]" in note
    unknown_line = next(l for l in note.splitlines() if unknown_imprint.id in l)
    assert "历史情绪印记" not in unknown_line
    # Recall is read-only: repeated recall does not reinforce the memory.
    before = {i.id: i.updated_at for i in store.list_active(lane_key=LANE, now=NOW)}
    again = store.context_for_lane(lane_key=LANE, now=NOW, query=TOPIC) or ""
    after = {i.id: i.updated_at for i in store.list_active(lane_key=LANE, now=NOW)}
    assert again == note and before == after
    assert EmotionalImprintStore(honey_home).get(unknown_imprint.id).status == "unknown"


# --------------------------------------------------------------------------- #
# Scenario 7: DeepSeek + Study external history (pure retrieval, shared cap)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_7_external_history_shared_cap(honey_home, monkeypatch):
    from honeyos.memory.runtime_context import build_silent_memory_context
    from honeyos.memory.runtime_shadow import run_cognitive_memory_shadow

    repo = CognitiveMemoryRepository(honey_home)
    for idx in range(3):
        repo.create_episode(
            episode_id=f"ds_{idx}", summary=f"HoneyOS 记忆系统 DeepSeek 记录 {idx}。",
            memory_origin="external", source_system="deepseek",
            source_scope="historical_import", source_key=f"ds-{idx}",
        )
    for idx in range(3):
        repo.create_episode(
            episode_id=f"st_{idx}", summary=f"HoneyOS 记忆系统 Study 记录 {idx}。",
            memory_origin="external", source_system="study",
            source_scope="historical_import", source_key=f"st-{idx}",
        )

    import honeyos.companion.physiology_shadow as phys

    monkeypatch.setattr(phys, "live_signals", lambda home, now=None: {"epinephrine": 0.99})
    result = run_cognitive_memory_shadow("HoneyOS 记忆系统", session_id="s7", turn_id="t1")
    assert len(result.selected) <= 3
    assert result.total_char_cost <= 900
    assert {item.source_system for item in result.selected} <= {"deepseek", "study"}

    context = build_silent_memory_context(
        query="HoneyOS 记忆系统",
        selected_memories=result.selected,
        current_turn_text="HoneyOS 记忆系统",
    )
    assert len(context.included) <= 3 and context.memory_chars <= 700

    # A suppressed source is never injected.
    repo.create_tombstone(
        scope="source", source_system="study", source_id="st-0",
        reason="user_explicit_forget",
    )
    again = run_cognitive_memory_shadow("HoneyOS 记忆系统", session_id="s7", turn_id="t2")
    assert all(item.id != "st_0" for item in again.selected)

    # No relevance match -> nothing injected.
    empty = run_cognitive_memory_shadow("今天午饭吃什么", session_id="s7", turn_id="t3")
    empty_context = build_silent_memory_context(
        query="今天午饭吃什么", selected_memories=empty.selected,
        current_turn_text="今天午饭吃什么",
    )
    assert empty.selected == () and empty_context.text == ""

    # External history can never become U2 evidence: U2 only resolves
    # continuity: refs, while external episodes live in a separate store.
    assert GatewayRunner._honeyos_u2_evidence_meta(
        honey_home, {0: "ds_0"}, LANE
    ) == {}


# --------------------------------------------------------------------------- #
# Scenario 8: real graph data flow (nodes, edges, imprint, forget, detach)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_scenario_8_graph_data_flow(honey_home):
    from honeyos.runtime.web_routers.understanding import (
        detach_understanding_evidence,
        get_understanding_graph,
        get_understanding_label,
        suppress_understanding_label,
    )

    result, _, _ = await _distill(honey_home, session="s8")
    memory_id = result.applied_indices[0]
    _seed_imprint(honey_home, memory_id, "known", "warmth", "温暖")

    graph = get_understanding_graph(lane="", namespace="", limit=50, offset=0)
    assert graph["total"] == 1
    label = graph["labels"][0]
    assert label["category_id"] == "behavior_pattern"
    assert label["created_at"] and label["updated_at"]
    evidence = label["evidence"]
    assert evidence[0]["relation"] == "support"
    assert evidence[0]["occurred_at"]
    assert evidence[0]["source_revision"]
    mem = evidence[0]["memory"]
    assert mem["created_at"]
    assert mem["imprint"]["status"] == "known"
    assert mem["imprint"]["label"] == "温暖"

    # Detail endpoint agrees with the graph listing.
    detail = get_understanding_label(label["id"])
    assert detail["id"] == label["id"] and detail["evidence"] == evidence

    # Detach one relation, then refresh reflects the removal.
    ref = evidence[0]["ref"]
    removed = detach_understanding_evidence(label["id"], ref=ref)
    assert removed["ok"] is True and removed["removed"] == 1
    assert get_understanding_label(label["id"])["evidence"] == []

    # A separate label: forgetting the LABEL hides its body but keeps the
    # native memory active (label-forget != memory-forget).
    store = StructuredMemoryStore(honey_home)
    keep = store.record(
        lane_key=LANE, kind="episode", content=f"{TOPIC}：一条用于标签忘记的记忆。",
        evidence="conversation_event", source_session_id="s8b",
        source_message_ids=(200,), created_by="background", now=NOW,
    )
    proposal = Proposal(
        operation="propose", category_id="interest_preference", scope_key="general",
        canonical_key="likes_deep_work", text="你偏好深度工作。",
        support_refs=(f"continuity:{keep.id}",),
    )
    apply_proposal(
        UnderstandingStore(honey_home / "understanding_v2.db"),
        owner=OWNER, lane=LANE, namespace="general", proposal=proposal,
        evidence_meta={f"continuity:{keep.id}": (keep.id, "s8b", keep.created_at.isoformat(), keep.created_at.isoformat())},
    )
    second = next(l for l in get_understanding_graph(lane="", namespace="", limit=50, offset=0)["labels"] if l["canonical_key"] == "likes_deep_work")
    suppressed = suppress_understanding_label(second["id"])
    assert suppressed["state"] == "user_suppressed"
    hidden = get_understanding_label(second["id"])
    assert hidden["suppressed"] is True and hidden["text"] == ""
    # The native memory is untouched by label suppression.
    assert _memory_status(honey_home, keep.id) == "active"
