from honeyos.agent.natural_chat_style import (
    CASUAL_CHAT_BLOCK,
    STRUCTURED_TASK_BLOCK,
    natural_chat_output_block,
)


def test_c1_casual_style_has_no_model_managed_bubble_count():
    block = natural_chat_output_block("我今天突然想到一件事")
    assert block == CASUAL_CHAT_BLOCK.strip()
    lowered = block.lower()
    assert "1–3" not in block
    assert "1-3" not in block
    assert "bubble" not in lowered
    assert "message-break" not in lowered


def test_c1_structured_style_preserves_task_structure():
    block = natural_chat_output_block("详细分析这个问题并按步骤给出方案")
    assert block == STRUCTURED_TASK_BLOCK.strip()
    assert "requested depth and structure" in block
    assert "Do not shorten away information" in block
