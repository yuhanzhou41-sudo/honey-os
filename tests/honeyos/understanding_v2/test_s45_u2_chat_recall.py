"""S4.5 Task A: U2 understanding enters chat context by topic, bounded.

These tests exercise the real read path used by ``build_turn_context``:
``u2_recall.recall_for_turn`` reads the postings index, revalidates evidence
against the live continuity store, and returns a short tagged block that the
existing ``compose_user_api_content`` (three-argument contract) sends to the
model.  They also lock the failure/edge behaviour: disabled, irrelevant,
suppressed, forgotten source, dedupe, and bounded recall.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from honeyos.agent.turn_context import compose_user_api_content
from honeyos.companion.continuity import StructuredMemoryStore
from honeyos.understanding.u2_contracts import Proposal
from honeyos.understanding.u2_maintenance import apply_proposal
from honeyos.understanding.u2_manage import suppress
from honeyos.understanding.u2_recall import recall_for_turn
from honeyos.understanding.u2_store import UnderstandingStore

OWNER, LANE, NS = "local-owner", "agent:main:api_server:dm:local-owner", "general"
BODY = "用户在学习新知识时倾向先理解原理 mechanism first"


def _enable(home: Path, enabled: bool = True) -> None:
    (home / "config.yaml").write_text(
        "memory:\n  distillation:\n    understanding:\n"
        f"      enabled: {'true' if enabled else 'false'}\n"
        f"      namespace: {NS}\n",
        encoding="utf-8",
    )


def _seed(home: Path, body: str = BODY, sessions: int = 2) -> tuple[str, str]:
    """One label backed by ``sessions`` active user-stated episodes."""
    store = StructuredMemoryStore(home)
    u2 = UnderstandingStore(home / "understanding_v2.db")
    u2.initialize()
    refs = []
    meta = {}
    for index in range(sessions):
        item = store.record(
            lane_key=LANE, kind="episode", content=f"记忆片段 {index}：{body}",
            evidence="user_stated", source_session_id=f"s{index}",
            importance="high", created_by="background",
            now=datetime.now(timezone.utc),
        )
        assert item is not None
        ref = f"continuity:{item.id}"
        refs.append(ref)
        meta[ref] = (item.id, f"s{index}", item.updated_at.isoformat(),
                     item.created_at.isoformat())
    label_id = apply_proposal(
        u2, owner=OWNER, lane=LANE, namespace=NS,
        proposal=Proposal("propose", "learning_work_style", "study",
                          "mechanism_first", body, tuple(refs), ()),
        evidence_meta=meta, continuity_db_path=home / "continuity.db",
    )
    return label_id, refs[0].split(":", 1)[1]


def test_relevant_topic_injects_label_into_final_api_content(tmp_path):
    _enable(tmp_path)
    _seed(tmp_path)
    recall = recall_for_turn(home=tmp_path, lane=LANE, query="我想学 mechanism 的学习方法")
    assert recall.text and BODY in recall.text
    api_content = compose_user_api_content("帮我把这个学明白", recall.text, "")
    assert api_content is not None
    assert BODY in api_content and "<memory-context>" in api_content
    # The clean stored user content is never mutated by the composition.
    assert "帮我把这个学明白" in api_content


def test_unrelated_topic_injects_nothing(tmp_path):
    _enable(tmp_path)
    _seed(tmp_path)
    recall = recall_for_turn(home=tmp_path, lane=LANE, query="今晚天气怎么样")
    assert recall.text == ""
    assert compose_user_api_content("今晚天气怎么样", recall.text, "") is None


def test_disabled_setting_keeps_original_chat_path(tmp_path):
    _enable(tmp_path, enabled=False)
    _seed(tmp_path)
    recall = recall_for_turn(home=tmp_path, lane=LANE, query="我想学 mechanism 的学习方法")
    assert recall.text == "" and recall.reason == "disabled"
    assert compose_user_api_content("你好", "", "") is None


def test_tentative_label_is_not_described_as_fact(tmp_path):
    _enable(tmp_path)
    _seed(tmp_path, sessions=1)
    recall = recall_for_turn(home=tmp_path, lane=LANE, query="mechanism 学习")
    assert recall.text
    assert "暂时理解" in recall.text
    assert "不是确定事实" in recall.text
    assert "已支持" not in recall.text


def test_user_suppressed_label_is_never_injected(tmp_path):
    _enable(tmp_path)
    label_id, _ = _seed(tmp_path)
    suppress(UnderstandingStore(tmp_path / "understanding_v2.db"), label_id,
             owner=OWNER, lane=LANE, namespace=NS)
    recall = recall_for_turn(home=tmp_path, lane=LANE, query="mechanism 学习")
    assert recall.text == ""


def test_forgotten_source_removes_label_from_recall(tmp_path):
    _enable(tmp_path)
    _, memory_id = _seed(tmp_path, sessions=1)
    assert StructuredMemoryStore(tmp_path).change_status(
        lane_key=LANE, item_id=memory_id, action="forget")
    recall = recall_for_turn(home=tmp_path, lane=LANE, query="mechanism 学习")
    assert recall.text == ""


def test_duplicate_of_native_memory_text_is_not_injected(tmp_path):
    _enable(tmp_path)
    _seed(tmp_path)
    recall = recall_for_turn(
        home=tmp_path, lane=LANE, query="mechanism 学习",
        known_text=f"共同经历：{BODY}",
    )
    assert recall.text == ""


def test_recall_is_capped_and_bounded(tmp_path):
    _enable(tmp_path)
    store = StructuredMemoryStore(tmp_path)
    u2 = UnderstandingStore(tmp_path / "understanding_v2.db")
    u2.initialize()
    for index in range(6):
        item = store.record(
            lane_key=LANE, kind="episode", content=f"学习 主题 {index}",
            evidence="user_stated", source_session_id="s1", importance="high",
            created_by="background", now=datetime.now(timezone.utc),
        )
        ref = f"continuity:{item.id}"
        apply_proposal(
            u2, owner=OWNER, lane=LANE, namespace=NS,
            proposal=Proposal("propose", "learning_work_style", "study",
                              f"theme_{index}", f"用户在学习主题{index}时倾向先列步骤",
                              (ref,), ()),
            evidence_meta={ref: (item.id, "s1", item.updated_at.isoformat(),
                                 item.created_at.isoformat())},
            continuity_db_path=tmp_path / "continuity.db",
        )
    recall = recall_for_turn(home=tmp_path, lane=LANE, query="学习 步骤 主题")
    assert recall.text
    assert len(recall.label_ids) <= 3
    assert len(recall.text) < 1200


def test_recall_makes_no_model_call(tmp_path, monkeypatch):
    _enable(tmp_path)
    _seed(tmp_path)

    async def _boom(*args, **kwargs):
        raise AssertionError("U2 chat recall must not call a model")

    import honeyos.agent.auxiliary_client as auxiliary_client

    monkeypatch.setattr(auxiliary_client, "async_call_llm", _boom)
    recall = recall_for_turn(home=tmp_path, lane=LANE, query="mechanism 学习")
    assert recall.text and BODY in recall.text


def test_current_correction_outranks_stored_understanding(tmp_path):
    _enable(tmp_path)
    _seed(tmp_path)
    recall = recall_for_turn(
        home=tmp_path, lane=LANE, query="其实我不是先理解原理，我更喜欢直接做题",
    )
    assert "以你此刻的说法为准" in recall.text
