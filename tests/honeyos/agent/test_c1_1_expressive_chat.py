from honeyos.agent.natural_chat_style import (
    CASUAL_CHAT_BLOCK,
    STRUCTURED_TASK_BLOCK,
    natural_chat_output_block,
)


def test_c1_1_casual_chat_allows_light_expressive_markers():
    block = natural_chat_output_block("终于下课了")
    assert block == CASUAL_CHAT_BLOCK.strip()
    assert "occasional emoji or kaomoji" in block
    assert "do not force one into every reply" in block
    assert "standalone reaction" in block


def test_c1_1_structured_tasks_avoid_decorative_expression():
    block = natural_chat_output_block("详细分析这个代码问题并给出步骤")
    assert block == STRUCTURED_TASK_BLOCK.strip()
    assert "Avoid decorative emoji or kaomoji" in block
