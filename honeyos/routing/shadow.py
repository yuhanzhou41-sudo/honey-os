from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .rules import route_by_rules
from .selective_loading import select_toolsets_for_route
from .turn_router import build_default_router

logger = logging.getLogger(__name__)


def _log_decision(decision, *, elapsed_ms: float, phase: str, configured_toolsets=()) -> None:
    # WARNING is intentional during shadow validation so journalctl shows it
    # with the gateway's current logging posture. Raw user text is never logged.
    selected_toolsets = select_toolsets_for_route(decision, configured_toolsets)
    logger.warning(
        "TURN_ROUTER_SHADOW phase=%s selected_groups=%s capabilities=%s "
        "configured_toolsets=%s selected_toolsets=%s "
        "intent=%s complexity=%s memory_mode=%s model_tier=%s "
        "confidence=%.3f source=%s elapsed_ms=%.1f",
        phase,
        list(decision.skill_groups),
        list(decision.capabilities),
        list(configured_toolsets),
        list(selected_toolsets),
        decision.intent,
        decision.complexity,
        decision.memory.mode,
        decision.model_tier,
        float(decision.confidence),
        decision.source,
        elapsed_ms,
    )


def _run_local_shadow(text: str, configured_toolsets=()) -> None:
    started = time.perf_counter()
    try:
        decision = build_default_router().route(text)
        _log_decision(
            decision,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            phase="local_async",
            configured_toolsets=configured_toolsets,
        )
    except Exception:
        logger.exception(
            "TURN_ROUTER_SHADOW phase=local_async failed elapsed_ms=%.1f",
            (time.perf_counter() - started) * 1000.0,
        )


def route_shadow_nonblocking(user_message: Any, *, configured_toolsets=()) -> None:
    """Observe routing without delaying the real turn.

    Deterministic rule routing runs synchronously.
    Ambiguous requests are classified by local Qwen on a daemon thread.
    Shadow output never changes enabled_toolsets.
    """
    text = str(user_message or "")
    started = time.perf_counter()

    try:
        decision = route_by_rules(text)
    except Exception:
        logger.exception("TURN_ROUTER_SHADOW phase=rules failed")
        return

    if decision is not None:
        _log_decision(
            decision,
            elapsed_ms=(time.perf_counter() - started) * 1000.0,
            phase="rules",
            configured_toolsets=configured_toolsets,
        )
        return

    logger.warning(
        "TURN_ROUTER_SHADOW phase=rules_ambiguous handoff=local_async "
        "elapsed_ms=%.1f",
        (time.perf_counter() - started) * 1000.0,
    )

    threading.Thread(
        target=_run_local_shadow,
        args=(text, tuple(configured_toolsets)),
        name="turn-router-shadow",
        daemon=True,
    ).start()
