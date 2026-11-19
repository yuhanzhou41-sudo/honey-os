from honeyos.agent.companion_input_budget import (
    MAX_INPUT_TOKENS,
    TARGET_INPUT_TOKENS,
    cap_history,
    estimate_wire_input,
    request_input_limit,
)


def test_history_growth_keeps_request_bounded_and_saves_current_tool_group():
    system = {"role": "system", "content": "Companion instructions"}
    earlier = [
        message
        for i in range(260)
        for message in [
            {"role": "user", "content": f"Turn {i}: " + "很多不同的背景信息。" * 30},
            {"role": "assistant", "content": "A long explanation. " * 60},
        ]
    ]
    latest = [
        {"role": "user", "content": "What happened now?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
        {"role": "tool", "tool_call_id": "c1", "content": "Tool result"},
    ]
    for history in (earlier[:160], earlier):
        full = [system, *history, *latest]
        payload = cap_history(full, [])
        assert payload[0] == system
        assert payload[1]["role"] == "user"
        assert payload[-3:] == latest
        assert estimate_wire_input({"messages": payload}, []) <= TARGET_INPUT_TOKENS
        assert len(payload) < len(full)
        assert full[-3:] == latest


def test_oversized_current_input_is_not_silently_truncated():
    message = {"role": "user", "content": "这段内容非常长。" * MAX_INPUT_TOKENS}
    assert cap_history([message], None) == [message]
    assert estimate_wire_input({"input": [message], "instructions": "system"}, []) > MAX_INPUT_TOKENS


def test_large_current_document_uses_model_window_before_older_history():
    latest = {"role": "user", "content": "保留整份资料的几个章节和专有名词。" * 1300}
    older = [{"role": "user", "content": "Older unrelated turn"}]
    limit = request_input_limit(65_536, 4096)
    estimate = estimate_wire_input({"messages": [latest]}, [])
    assert MAX_INPUT_TOKENS < estimate < limit
    assert cap_history([*older, latest], None, input_limit=limit) == [latest]
    assert request_input_limit(8192) < estimate
