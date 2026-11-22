from honeyos.understanding.u2_context import (
    UNDERSTANDING_BEGIN, compose_memory_context, strip_understanding,
)
from honeyos.understanding.u2_contracts import ContextSegment


def test_shared_budget_dedupes_and_marks_derived_text():
    segments = (
        ContextSegment("user", "user.md", "1", "user", "self", "原用户资料", 6, 4),
        ContextSegment("dup", "user.md", "1", "memory", "self", "重复", 6, 4),
        ContextSegment("graph", "label:1", "2", "understanding", "inference", "可能偏好机制", 8, 4),
        ContextSegment("stale", "label:2", "1", "understanding", "inference", "旧理解", 2, 3),
    )
    result = compose_memory_context(segments, total_budget=20, graph_budget=10,
                                    current_policy_epoch=4)
    assert result.segment_ids == ("user", "graph")
    assert result.token_cost == 14
    assert result.text.count("原用户资料") == 1
    assert UNDERSTANDING_BEGIN in result.text
    assert "不是已验证事实" in result.text
    assert "旧理解" not in result.text


def test_graph_budget_and_revocation_strip_only_derived_block():
    item = ContextSegment("g", "l", "1", "understanding", "inference", "派生正文", 11, 1)
    assert not compose_memory_context((item,), total_budget=20, graph_budget=10,
                                      current_policy_epoch=1).text
    marked = compose_memory_context((item,), total_budget=20, graph_budget=12,
                                    current_policy_epoch=1).text
    assert strip_understanding("原问题\n\n" + marked) == "原问题"
