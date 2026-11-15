from __future__ import annotations

import hashlib
import json

from honeyos.agent.context_trace import write_context_source_trace


def test_g0_context_trace_is_metadata_only(tmp_path):
    p = tmp_path / "trace.jsonl"
    secrets = [
        "SYS_SECRET",
        "HIST_SECRET",
        "USER_SECRET",
        "NATIVE_SECRET",
        "COG_SECRET",
        "PLUGIN_SECRET",
    ]

    write_context_source_trace(
        session_id="s1",
        turn_id="t1",
        query_namespace="general",
        system_prompt=secrets[0],
        history_messages=[
            {"role": "user", "content": secrets[1]},
            {"role": "assistant", "content": "answer"},
        ],
        clean_user_message=secrets[2],
        native_memory_context=secrets[3],
        cognitive_context=secrets[4],
        cognitive_item_count=2,
        plugin_user_context=secrets[5],
        final_memory_context=secrets[3] + secrets[4],
        api_content=secrets[2] + secrets[3] + secrets[4] + secrets[5],
        path=p,
    )

    raw = p.read_text(encoding="utf-8")
    for secret in secrets:
        assert secret not in raw

    row = json.loads(raw)
    assert row["phase"] == "G0.3"
    assert "session_id" not in row
    assert row["session_sha256"] == hashlib.sha256(b"s1").hexdigest()
    assert row["query_namespace"] == "general"
    assert row["history"]["messages"] == 2
    assert row["history"]["role_counts"] == {"user": 1, "assistant": 1}
    assert row["current_turn"]["cognitive_item_count"] == 2
    assert len(row["system_prompt"]["sha256"]) == 64


def test_g0_context_trace_fail_open(tmp_path):
    directory = tmp_path / "as_dir"
    directory.mkdir()
    write_context_source_trace(
        session_id="s",
        turn_id="t",
        query_namespace="",
        system_prompt="x",
        history_messages=[],
        clean_user_message="x",
        native_memory_context="",
        cognitive_context="",
        cognitive_item_count=0,
        plugin_user_context="",
        final_memory_context="",
        api_content="x",
        path=directory,
    )


def test_trace_is_opt_in_and_uses_current_profile_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path))
    monkeypatch.delenv("HONEYOS_CONTEXT_TRACE", raising=False)
    args = dict(
        session_id="private-session-marker",
        turn_id="private-turn-marker",
        query_namespace="private-namespace-marker",
        system_prompt="private-system-marker",
        history_messages=[{"role": "private-role-marker", "content": "private-content"}],
        clean_user_message="private-question",
        native_memory_context="",
        cognitive_context="",
        cognitive_item_count=0,
        plugin_user_context="",
        final_memory_context="",
        api_content="private-question",
    )
    trace = tmp_path / "memory" / "runtime_context_sources.jsonl"
    write_context_source_trace(**args)
    assert not trace.exists()

    monkeypatch.setenv("HONEYOS_CONTEXT_TRACE", "1")
    write_context_source_trace(**args)
    raw = trace.read_text()
    assert "private-" not in raw
    row = json.loads(raw)
    assert row["query_namespace"] == ""
    assert row["history"]["role_counts"] == {"unknown": 1}
