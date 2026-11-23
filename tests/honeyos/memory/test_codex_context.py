from __future__ import annotations

from types import SimpleNamespace

import pytest

from honeyos.memory.codex_context import (
    MAX_CODEX_CONTEXT_CHARS,
    build_codex_context,
    codex_context_mode,
)
from honeyos.memory.repository import CognitiveMemoryRepository
from honeyos.memory.runtime_shadow import ShadowCandidate, ShadowRetrievalResult

SCOPED_ACTIVE = {
    "memory": {"cognitive": {"context_mode": "active", "codex_context_mode": "scoped"}}
}


def _access(**updates):
    access = {
        "owner": "User",
        "lane": "lane-a",
        "session_scope": "lane",
        "chat_type": "dm",
        "purposes": ["codex"],
    }
    access.update(updates)
    return access


def _repo(tmp_path, *, access=None, summary="用户以前喜欢夜跑。", eid="m1"):
    repo = CognitiveMemoryRepository(db_path=tmp_path / "cognitive.sqlite")
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
    return repo


def _shadow(eid="m1", summary="用户以前喜欢夜跑。"):
    candidate = ShadowCandidate(
        id=eid,
        source_system="deepseek",
        source_key=f"source-{eid}",
        partition="personal",
        score=5.0,
        reason="lexical:test",
        selected=True,
        char_cost=len(summary),
        summary_preview=summary,
    )
    return ShadowRetrievalResult(
        query="我最近还想跑步",
        namespace="general",
        selected=(candidate,),
        rejected=(),
        total_char_cost=candidate.char_cost,
    )


def _agent(**overrides):
    values = {
        "session_id": "session-a",
        "_companion_memory_owner": "User",
        "_companion_memory_lane": "lane-a",
        "_companion_memory_chat_type": "dm",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def patched_retrieval(monkeypatch):
    import honeyos.memory.runtime_shadow as runtime_shadow

    monkeypatch.setattr(
        runtime_shadow,
        "run_cognitive_memory_shadow",
        lambda query, **kwargs: _shadow(),
    )
    return runtime_shadow


def test_codex_context_mode_defaults_to_off():
    assert codex_context_mode({}) == "off"
    assert codex_context_mode({"memory": {"cognitive": {}}}) == "off"
    assert codex_context_mode({"memory": {"cognitive": {"codex_context_mode": "weird"}}}) == "off"
    assert (
        codex_context_mode({"memory": {"cognitive": {"codex_context_mode": "scoped"}}})
        == "scoped"
    )


def test_codex_context_is_off_by_default(tmp_path, patched_retrieval):
    repo = _repo(tmp_path)
    assert (
        build_codex_context(
            _agent(), "我最近还想跑步", repository=repo, config={}
        )
        == ""
    )


def test_codex_context_requires_active_cognitive_gate(tmp_path, patched_retrieval):
    repo = _repo(tmp_path)
    shadow_gate = {"memory": {"cognitive": {"context_mode": "shadow", "codex_context_mode": "scoped"}}}
    assert (
        build_codex_context(
            _agent(), "我最近还想跑步", repository=repo, config=shadow_gate
        )
        == ""
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"_companion_memory_owner": ""},
        {"_companion_memory_lane": ""},
        {"_companion_memory_chat_type": ""},
        {"session_id": ""},
    ],
)
def test_codex_context_requires_complete_scope(
    tmp_path, patched_retrieval, overrides
):
    repo = _repo(tmp_path)
    assert (
        build_codex_context(
            _agent(**overrides),
            "我最近还想跑步",
            repository=repo,
            config=SCOPED_ACTIVE,
        )
        == ""
    )


def test_codex_context_injects_only_codex_purpose(tmp_path, patched_retrieval):
    repo = _repo(tmp_path)
    audit = tmp_path / "audit.jsonl"
    text = build_codex_context(
        _agent(),
        "我最近还想跑步",
        repository=repo,
        audit_path=audit,
        config=SCOPED_ACTIVE,
    )
    assert "用户以前喜欢夜跑" in text
    assert len(text) <= MAX_CODEX_CONTEXT_CHARS
    assert "system prompt" not in text.lower()


def test_codex_context_denies_chat_only_purpose(tmp_path, patched_retrieval):
    repo = _repo(tmp_path, access=_access(purposes=["chat"]))
    audit = tmp_path / "audit.jsonl"
    assert (
        build_codex_context(
            _agent(),
            "我最近还想跑步",
            repository=repo,
            audit_path=audit,
            config=SCOPED_ACTIVE,
        )
        == ""
    )
    rows = audit.read_text(encoding="utf-8").splitlines() if audit.exists() else []
    assert any("purpose_mismatch" in row for row in rows)


@pytest.mark.parametrize(
    "access_update",
    [
        {"owner": "Someone"},
        {"lane": "lane-b"},
        {"chat_type": "group"},
    ],
)
def test_codex_context_denies_cross_scope(tmp_path, patched_retrieval, access_update):
    repo = _repo(tmp_path, access=_access(**access_update))
    assert (
        build_codex_context(
            _agent(),
            "我最近还想跑步",
            repository=repo,
            audit_path=tmp_path / "audit.jsonl",
            config=SCOPED_ACTIVE,
        )
        == ""
    )


def test_codex_context_caps_long_payload(tmp_path, monkeypatch):
    long_summary = "用户以前喜欢夜跑。" + "细节" * 400
    repo = _repo(tmp_path, summary=long_summary)
    import honeyos.memory.runtime_shadow as runtime_shadow

    monkeypatch.setattr(
        runtime_shadow,
        "run_cognitive_memory_shadow",
        lambda query, **kwargs: _shadow(summary=long_summary),
    )
    text = build_codex_context(
        _agent(),
        "我最近还想跑步",
        repository=repo,
        audit_path=tmp_path / "audit.jsonl",
        config=SCOPED_ACTIVE,
    )
    assert text
    assert len(text) <= MAX_CODEX_CONTEXT_CHARS
