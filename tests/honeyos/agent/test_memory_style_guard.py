from honeyos.agent.memory_style_guard import (
    NATURAL_MEMORY_EXPRESSION_BLOCK,
    natural_memory_expression_block,
)


def test_natural_memory_expression_block_core_rules():
    block = natural_memory_expression_block()
    assert block == NATURAL_MEMORY_EXPRESSION_BLOCK.strip()
    assert "Do not announce that you retrieved" in block
    assert "Current user statements always override remembered context." in block
    assert "explicitly asks what you remember" in block


def test_natural_memory_expression_block_no_behavioral_retrieval_logic():
    block = natural_memory_expression_block()
    forbidden_codeish = ("SELECT ", "sqlite", "source_key", "score >")
    assert not any(x in block for x in forbidden_codeish)

def test_natural_memory_expression_block_allows_explicit_provenance_questions():
    block = natural_memory_expression_block()
    assert "explicitly asks what you remember" in block
    assert "where information came from" in block
    normalized = " ".join(block.split())
    assert "answer that question transparently" in normalized
