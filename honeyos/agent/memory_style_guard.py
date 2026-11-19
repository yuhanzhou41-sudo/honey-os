"""G1.1 per-turn wording guidance for existing remembered context."""

NATURAL_MEMORY_EXPRESSION_BLOCK = """## Natural use of remembered context

Use relevant remembered facts naturally and only where they help answer the request.
Do not announce that you retrieved or searched memory in ordinary conversation.
When the user explicitly asks what you remember or where information came from,
answer that question transparently. Explain only the source you can substantiate.
Preserve any requested structure and citations for the task.
Current user statements always override remembered context.
"""


def natural_memory_expression_block() -> str:
    return NATURAL_MEMORY_EXPRESSION_BLOCK.strip()
