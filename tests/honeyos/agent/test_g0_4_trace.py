from __future__ import annotations

import json

from honeyos.agent.g0_4_trace import write_g0_4_runtime_trace


def test_g0_4_trace_metadata_only(tmp_path):
    path = tmp_path / "g04.jsonl"

    secrets = {
        "system": "# Identity\nSECRET SYSTEM\n# Memory\nUse memory silently.",
        "hook": "SECRET HOOK",
        "time": "SECRET TIME",
        "notes": "SECRET NOTES",
    }
    final = "\n\n".join([secrets["hook"], secrets["time"], secrets["notes"]])

    write_g0_4_runtime_trace(
        session_id="s",
        turn_id="t",
        system_prompt=secrets["system"],
        plugin_final_context=final,
        plugin_hook_context=secrets["hook"],
        runtime_time_context=secrets["time"],
        gateway_notes_context=secrets["notes"],
        path=path,
    )

    raw = path.read_text(encoding="utf-8")
    for value in secrets.values():
        assert value not in raw

    row = json.loads(raw)
    assert row["phase"] == "G0.4"
    assert row["plugin_sidecar"]["pre_llm_hook_chars"] == len(secrets["hook"])
    assert row["plugin_sidecar"]["runtime_time_context_chars"] == len(secrets["time"])
    assert row["plugin_sidecar"]["gateway_notes_chars"] == len(secrets["notes"])
    assert row["system_prompt"]["section_count"] == 2
    assert row["system_prompt"]["keyword_counts"]["memory"] >= 1


def test_g0_4_trace_fail_open(tmp_path):
    directory = tmp_path / "dir"
    directory.mkdir()

    write_g0_4_runtime_trace(
        session_id="s",
        turn_id="t",
        system_prompt="x",
        plugin_final_context="",
        plugin_hook_context="",
        runtime_time_context="",
        gateway_notes_context="",
        path=directory,
    )
