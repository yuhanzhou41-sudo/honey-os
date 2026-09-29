"""G1.2 natural chat style with explicit intent-aware modes.

Expression-only. No retrieval, memory, persistence, or tool behavior changes.
"""

from __future__ import annotations

import re

STRUCTURED_INTENT_PATTERNS = (
    r"详细",
    r"对比",
    r"比较",
    r"按.+列",
    r"按模块",
    r"分模块",
    r"步骤",
    r"逐步",
    r"分析",
    r"总结",
    r"整理",
    r"列出",
    r"表格",
    r"清单",
    r"代码",
    r"调试",
    r"文档",
    r"报告",
    r"论文",
    r"explain in detail",
    r"compare",
    r"step[- ]by[- ]step",
    r"analy[sz]e",
    r"list",
    r"table",
)

CASUAL_CHAT_BLOCK = """## Natural conversational response style — ordinary conversation

This is an ordinary conversational turn, not a report request.

- Answer or react to the point immediately.
- Prefer naturally sized conversational clauses and sentences instead of a mini essay.
- Do not force a fixed number of paragraphs or messages; the HoneyOS delivery layer
  handles streaming chat boundaries separately.
- Do not use headings, numbered sections, "first/second/third", or exhaustive lists
  unless the user explicitly asks for structure.
- Mention only the most relevant background. Do not dump every related fact or memory.
- If uncertain, state the uncertainty briefly and proportionally.
- Do not add a concluding summary, takeaway, recommendation, or next-step offer unless
  it is genuinely needed for the user\'s question.
- Keep the tone conversational rather than explanatory-documentary.
- Do not restate the question.
- In casual chat, an occasional emoji or kaomoji is welcome when it fits naturally; do not force one into every reply.
- A brief standalone reaction such as "🥺" or "(´▽｀)" is fine when that is more natural than another sentence.
"""

STRUCTURED_TASK_BLOCK = """## Natural conversational response style — structured task

The user is explicitly asking for detail, analysis, comparison, steps, or structured output.

- Give the requested depth and structure.
- Preserve requested headings, modules, lists, tables, steps, or technical detail.
- Do not shorten away information needed to complete the task.
- Still avoid unnecessary repetition, filler, provenance narration, or generic conclusions.
- Avoid decorative emoji or kaomoji in substantive output unless the user explicitly asks for them or they are genuinely useful.
"""


def is_structured_output_request(user_text: object) -> bool:
    if not isinstance(user_text, str):
        return False
    text = user_text.strip().lower()
    if not text:
        return False
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in STRUCTURED_INTENT_PATTERNS)


def natural_chat_output_block(user_text: object = "") -> str:
    if is_structured_output_request(user_text):
        return STRUCTURED_TASK_BLOCK.strip()
    return CASUAL_CHAT_BLOCK.strip()
