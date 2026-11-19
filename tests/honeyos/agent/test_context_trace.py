from __future__ import annotations

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


def test_runtime_delta_semantics_documented():
    native = "abc"
    final = native + "\nCOGNITIVE"
    cognitive = final[len(native):] if final.startswith(native) else ""
    assert cognitive == "\nCOGNITIVE"
    history = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "current"},
    ]
    current_turn_user_idx = 2
    assert history[:current_turn_user_idx] == history[:2]
