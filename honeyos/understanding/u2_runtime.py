"""Fail-closed off/shadow/active runtime boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from threading import BoundedSemaphore
from typing import Callable, TypeVar

from .u2_context import strip_understanding

T = TypeVar("T")
_WORKERS = ThreadPoolExecutor(max_workers=2, thread_name_prefix="honey-u2")
_SLOTS = BoundedSemaphore(2)


class RuntimeMode(StrEnum):
    OFF = "off"
    SHADOW = "shadow"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class RuntimeResult:
    context: str = ""
    candidate_count: int = 0
    estimated_tokens: int = 0
    injected: bool = False
    state_axis_verified: bool = False
    reason: str = ""


def expose(mode: RuntimeMode, *, context: str, candidate_count: int,
           estimated_tokens: int, active_authorized: bool = False) -> RuntimeResult:
    if mode == RuntimeMode.OFF:
        return RuntimeResult()
    if mode == RuntimeMode.SHADOW:
        return RuntimeResult(candidate_count=candidate_count,
                             estimated_tokens=estimated_tokens)
    if not active_authorized:
        raise PermissionError("active understanding requires an authorized environment")
    return RuntimeResult(context=context, candidate_count=candidate_count,
                         estimated_tokens=estimated_tokens, injected=bool(context))


def bounded_call(call: Callable[[], T], *, timeout_seconds: float) -> T:
    """Run a blocking resolver with a total deadline and bounded late work."""
    if timeout_seconds <= 0:
        raise TimeoutError("understanding deadline exhausted")
    if not _SLOTS.acquire(blocking=False):
        raise TimeoutError("understanding worker capacity exhausted")
    future = _WORKERS.submit(call)
    future.add_done_callback(lambda _future: _SLOTS.release())
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeout as exc:
        future.cancel()
        raise TimeoutError("understanding deadline exceeded") from exc


def normalize_state_bias(value: object) -> tuple[float, bool]:
    """Normalize an optional verified axis; absent/invalid state is neutral."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0, False
    return max(-0.15, min(0.15, float(value))), True


def sanitize_replay(content: object, *, policy_epoch_matches: bool) -> object:
    """Never replay derived text after a management epoch change."""
    if not isinstance(content, str):
        return content
    return content if policy_epoch_matches else strip_understanding(content)

