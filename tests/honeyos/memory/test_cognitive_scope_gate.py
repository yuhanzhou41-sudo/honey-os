from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from honeyos.memory.repository import CognitiveMemoryRepository
from honeyos.memory.runtime_context import (
    MAX_ITEMS,
    MAX_MEMORY_PAYLOAD_CHARS,
    MemoryRequestScope,
    authorize_silent_memory_context,
    build_silent_memory_context,
    cognitive_memory_context_mode,
    inject_silent_memory_context,
)
from honeyos.memory.runtime_shadow import (
    CognitiveMemoryShadowRetriever,
    ShadowCandidate,
    ShadowRetrievalResult,
)


BASE_SCOPE = MemoryRequestScope(
    owner="User",
    lane="lane-a",
    session_id="session-a",
    chat_type="dm",
)


def _access(**updates):
    access = {
        "owner": "User",
        "lane": "lane-a",
        "session_scope": "lane",
        "chat_type": "dm",
        "purposes": ["chat"],
    }
    access.update(updates)
    return access


def _add(
    repo,
    eid="m1",
    summary="用户以前喜欢阅读。",
    *,
    access=None,
    status="active",
):
    repo.create_episode(
        episode_id=eid,
        episode_type="historical_external",
        summary=summary,
        occurred_at="2024-04-13T19:00:00+08:00",
        memory_origin="external",
        source_system="deepseek",
        source_scope="historical_import",
        source_key=f"source-{eid}",
        metadata={"access": access or _access()},
    )
    if status != "active":
        with repo.connect() as db:
            db.execute(
                "UPDATE memory_episodes SET status=? WHERE episode_id=?",
                (status, eid),
            )
    return eid


def _candidate(eid="m1", summary="用户以前喜欢阅读。", *, partition="personal"):
    return ShadowCandidate(
        id=eid,
        source_system="deepseek",
        source_key=f"source-{eid}",
        partition=partition,
        score=5.0,
        reason="lexical:test",
        selected=True,
        char_cost=len(summary),
        summary_preview=summary,
    )


def _context(candidates, *, namespace="general"):
    return build_silent_memory_context(
        query="回忆以前的相关记录",
        selected_memories=candidates,
        current_turn_text="回忆以前的相关记录",
        current_namespace=namespace,
    )


def _shadow(candidate, *, namespace="general", explicit_recall=False):
    return ShadowRetrievalResult(
        query="回忆以前的相关记录",
        namespace=namespace,
        selected=(candidate,),
        rejected=(),
        total_char_cost=candidate.char_cost,
        explicit_recall=explicit_recall,
    )


def _authorize(context, shadow, repo, scope=BASE_SCOPE, audit_path=None):
    return authorize_silent_memory_context(
        context,
        shadow,
        scope=scope,
        repository=repo,
        session_id=scope.session_id,
        turn_id="turn-1",
        audit_path=audit_path,
    )


def _assert_denied(result, reason):
    assert result.included == ()
    assert result.text == ""
    assert reason in {item.reason for item in result.rejected}


def test_normal_dm_allows_matching_access_and_audit_has_no_private_text(tmp_path):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    _add(repo)
    candidate = _candidate()
    audit = tmp_path / "audit.jsonl"

    result = _authorize(_context((candidate,)), _shadow(candidate), repo, audit_path=audit)

    assert [item.memory_id for item in result.included] == ["m1"]
    raw = audit.read_text(encoding="utf-8")
    row = json.loads(raw.strip())
    assert row["phase"] == "S1"
    assert row["included_ids"] == ["m1"]
    assert "用户以前喜欢阅读" not in raw
    assert "source-m1" not in raw


@pytest.mark.parametrize(
    ("scope", "access", "reason"),
    [
        (replace(BASE_SCOPE, lane="lane-b"), None, "lane_mismatch"),
        (replace(BASE_SCOPE, owner="Honey"), None, "owner_mismatch"),
        (
            replace(BASE_SCOPE, session_id="session-b"),
            _access(session_scope="session", session_id="session-a"),
            "session_mismatch",
        ),
        (replace(BASE_SCOPE, chat_type="group"), None, "chat_type_mismatch"),
        (replace(BASE_SCOPE, purpose="work"), None, "purpose_mismatch"),
    ],
)
def test_cross_scope_and_purpose_are_fail_closed(tmp_path, scope, access, reason):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    _add(repo, access=access)
    candidate = _candidate()

    result = _authorize(_context((candidate,)), _shadow(candidate), repo, scope=scope)

    _assert_denied(result, reason)


def test_missing_access_and_missing_repository_never_inject(tmp_path):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    _add(repo)
    with repo.connect() as db:
        db.execute("UPDATE memory_episodes SET metadata_json='{}' WHERE episode_id='m1'")
    candidate = _candidate()
    context = _context((candidate,))
    shadow = _shadow(candidate)

    _assert_denied(_authorize(context, shadow, repo), "access_missing")
    merged = inject_silent_memory_context(
        "NATIVE",
        context,
        shadow,
        mode="active",
        scope=BASE_SCOPE,
        repository=None,
        audit_path=tmp_path / "audit.jsonl",
    )
    assert merged == "NATIVE"


def test_roleplay_cannot_enter_real_namespace_even_with_matching_access(tmp_path):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    summary = "【虚构角色扮演】吸血鬼剧情。"
    _add(repo, summary=summary)
    candidate = _candidate(summary=summary, partition="roleplay")
    context = _context((candidate,), namespace="roleplay")
    assert context.would_inject

    result = _authorize(context, _shadow(candidate, namespace="general"), repo)

    _assert_denied(result, "namespace_mismatch")


def test_dormant_memory_requires_explicit_recall(tmp_path):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    _add(repo, status="dormant")
    candidate = _candidate()
    context = _context((candidate,))

    _assert_denied(
        _authorize(context, _shadow(candidate), repo),
        "dormant_without_explicit_recall",
    )
    allowed = _authorize(
        context,
        _shadow(candidate, explicit_recall=True),
        repo,
    )
    assert [item.memory_id for item in allowed.included] == ["m1"]


def test_explicit_archive_recall_marks_shadow_result_and_keeps_study_salience(tmp_path):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    _add(repo, "old", "散步时闻到雨后泥土味。", status="dormant")
    _add(repo, "emphasis", "The backup was available on a spare disk.")
    _add(repo, "arousal", "The missing backup caused a surprise.")
    now = datetime(2026, 11, 17, tzinfo=timezone.utc)
    with repo.connect() as db:
        db.execute(
            "UPDATE memory_episodes SET occurred_at='2026-11-16T19:00:00+08:00' "
            "WHERE episode_id IN ('emphasis','arousal')"
        )
        db.executemany(
            "INSERT INTO memory_salience "
            "(memory_kind,memory_id,user_emphasis,arousal,updated_at) "
            "VALUES ('episode',?,?,?,'2026-11-17')",
            [("emphasis", 0.45, 0), ("arousal", 0, 1)],
        )
    retriever = CognitiveMemoryShadowRetriever(repo)

    recalled = retriever.retrieve(
        "回顾 2024年4月12日 至 2024年4月13日 的聊天记录",
        adaptive=True,
        now=now,
        write_audit=False,
    )
    ordered = retriever.retrieve("backup", adaptive=True, now=now, write_audit=False)

    assert recalled.explicit_recall is True
    assert [item.id for item in recalled.selected] == ["old"]
    assert [item.id for item in ordered.selected] == ["emphasis", "arousal"]


def test_source_revocation_is_rechecked_at_injection_time(tmp_path):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    _add(repo)
    candidate = _candidate()
    context = _context((candidate,))
    shadow = _shadow(candidate)
    audit = tmp_path / "audit.jsonl"
    assert _authorize(context, shadow, repo, audit_path=audit).would_inject

    repo.create_tombstone(
        scope="source",
        source_system="deepseek",
        source_id="source-m1",
        reason="test_revocation",
    )
    merged = inject_silent_memory_context(
        "NATIVE",
        context,
        shadow,
        mode="active",
        scope=BASE_SCOPE,
        repository=repo,
        audit_path=audit,
    )

    assert merged == "NATIVE"
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    assert any(
        rejected["reason"] == "source_tombstoned"
        for row in rows
        for rejected in row.get("rejected", [])
    )
    assert "用户以前喜欢阅读" not in audit.read_text(encoding="utf-8")


@pytest.mark.parametrize("mode", ["off", "shadow", "active", "invalid"])
def test_context_mode_gate_controls_model_visibility(tmp_path, mode):
    config = {"memory": {"cognitive": {"context_mode": mode}}}
    expected_mode = mode if mode in {"off", "shadow", "active"} else "shadow"
    assert cognitive_memory_context_mode(config) == expected_mode

    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    _add(repo)
    candidate = _candidate()
    merged = inject_silent_memory_context(
        "NATIVE",
        _context((candidate,)),
        _shadow(candidate),
        mode=mode,
        scope=BASE_SCOPE,
        repository=repo,
        audit_path=tmp_path / "audit.jsonl",
    )
    if expected_mode == "active":
        assert "用户以前喜欢阅读" in merged
    else:
        assert merged == "NATIVE"


def test_missing_mode_defaults_to_shadow():
    assert cognitive_memory_context_mode({}) == "shadow"
    assert cognitive_memory_context_mode({"memory": {"cognitive": None}}) == "shadow"


def test_authorized_context_preserves_item_and_character_limits(tmp_path):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
    candidates = []
    for index in range(5):
        eid = f"m{index}"
        summary = f"用户过去记录了项目事件 {index}。"
        _add(repo, eid, summary)
        candidates.append(_candidate(eid, summary))
    context = _context(candidates)
    shadow = ShadowRetrievalResult(
        query="回忆以前的相关记录",
        namespace="general",
        selected=tuple(candidates),
        rejected=(),
        total_char_cost=sum(item.char_cost for item in candidates),
    )

    result = _authorize(context, shadow, repo)

    assert len(result.included) == MAX_ITEMS
    assert result.memory_chars <= MAX_MEMORY_PAYLOAD_CHARS
    assert sum(item.reason == "result_limit" for item in result.rejected) == 2
