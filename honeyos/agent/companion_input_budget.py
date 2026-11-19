"""Bound browser companion input without modifying stored conversation history."""
from typing import Any

from honeyos.agent.model_metadata import estimate_request_tokens_rough

TARGET_INPUT_TOKENS = 12_000
MAX_INPUT_TOKENS = 16_000


def request_input_limit(context_window: Any, output_tokens: Any = None) -> int:
    """Reserve output and a margin for estimator/provider differences."""
    if type(context_window) is not int or context_window <= 0:
        return MAX_INPUT_TOKENS
    output = output_tokens if type(output_tokens) is int and output_tokens > 0 else 0
    reserve = max(min(output, context_window // 4), min(8192, context_window // 5))
    return max(0, context_window - reserve - max(256, context_window // 20))


def fit_output_to_window(payload: dict[str, Any], context_window: Any, estimated_input: int) -> None:
    if type(context_window) is not int or context_window <= 0:
        return
    remaining = max(1, context_window - estimated_input - max(256, context_window // 20))
    for key in ("max_tokens", "max_completion_tokens", "max_output_tokens"):
        value = payload.get(key)
        if type(value) is int and value > remaining:
            payload[key] = remaining


def cap_history(
    messages: list[dict], tools: list[dict] | None, *, input_limit: int = MAX_INPUT_TOKENS,
) -> list[dict]:
    target = min(TARGET_INPUT_TOKENS, input_limit)
    if estimate_request_tokens_rough(messages, tools=tools) <= target:
        return messages
    # Retain the system prefix and whole user-led exchanges, which preserves
    # the current request and the association between tool calls and results.
    starts = [index for index, message in enumerate(messages) if message.get("role") == "user"]
    if not starts:
        return messages
    first = starts[0]
    prefix = [message for message in messages[:first] if message.get("role") in {"system", "developer"}]
    left, right = 1, len(starts) - 1
    while left < right:
        middle = (left + right) // 2
        candidate = prefix + messages[starts[middle]:]
        if estimate_request_tokens_rough(candidate, tools=tools) <= target:
            right = middle
        else:
            left = middle + 1
    return prefix + messages[starts[min(left, len(starts) - 1)]:]


def estimate_wire_input(payload: dict[str, Any], original_messages: list[dict]) -> int:
    messages = payload.get("messages", payload.get("input", original_messages))
    if isinstance(messages, str):
        messages = [{"content": messages}]
    elif not isinstance(messages, list):
        messages = original_messages

    # Responses input_image is a part inside a content array. The same
    # estimator already accounts for that shape and standard chat messages.
    system = payload.get("instructions", payload.get("system", ""))
    return estimate_request_tokens_rough(
        messages, system_prompt=str(system or ""), tools=payload.get("tools")
    )
