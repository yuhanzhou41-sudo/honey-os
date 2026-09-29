from honeyos.agent.natural_chat_style import (
    CASUAL_CHAT_BLOCK,
    STRUCTURED_TASK_BLOCK,
    is_structured_output_request,
    natural_chat_output_block,
)


def test_g1_2_casual_turn_gets_short_conversational_mode():
    assert not is_structured_output_request("我今天有点犯困")
    assert not is_structured_output_request("你觉得最麻烦的地方是什么？")
    block = natural_chat_output_block("你觉得最麻烦的地方是什么？")
    assert block == CASUAL_CHAT_BLOCK.strip()
    assert "Prefer naturally sized conversational clauses and sentences" in block
    assert "Do not force a fixed number of paragraphs or messages" in block
    assert "1–3 short paragraphs" not in block
    assert "Do not use headings, numbered sections" in block


def test_g1_2_explicit_structured_task_preserves_depth():
    prompts = [
        "帮我详细对比一下两个系统，按模块列出来",
        "请分步骤分析这个问题",
        "整理成表格",
        "compare these two designs in detail",
    ]
    for prompt in prompts:
        assert is_structured_output_request(prompt)
        assert natural_chat_output_block(prompt) == STRUCTURED_TASK_BLOCK.strip()


def test_g1_2_ordinary_technical_question_is_not_automatically_report_mode():
    prompt = "HoneyOS 的记忆系统之前是怎么规划的？"
    assert not is_structured_output_request(prompt)
    block = natural_chat_output_block(prompt)
    assert "ordinary conversational turn" in block


def test_g1_2_no_retrieval_or_tool_behavior():
    joined = CASUAL_CHAT_BLOCK + STRUCTURED_TASK_BLOCK
    forbidden = ("sqlite", "source_key", "query_namespace", "tombstone", "tool permission")
    assert not any(x in joined for x in forbidden)
