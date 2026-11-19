from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore

from .rules import route_by_rules
from .turn_router import build_default_router

logger = logging.getLogger(__name__)
_CLASSIFY_BUDGET_SECONDS = 3.0
_MIN_CLASSIFY_CONFIDENCE = 0.65
# One shared worker; requests never queue behind a timed-out classification.
_classifier_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="turn-router")
_classifier_slot = BoundedSemaphore(1)

ALWAYS_ON_TOOLSETS = frozenset({
    "companion_profile",
    "companion_memory",
    "proactive_companion",
})

ROUTE_TOOLSETS = {
    "memory": frozenset({"memory", "session_search"}),
    "files": frozenset({"file"}),
    "coding": frozenset({"code_execution", "terminal", "file"}),
    "research": frozenset({"web"}),
    "automation": frozenset({"todo", "cronjob"}),
    "media": frozenset({"vision", "tts", "image_gen"}),
    "system": frozenset({"terminal", "code_execution"}),
    "study": frozenset({"skills"}),
    "communication": frozenset(),
}

CAPABILITY_TOOLSETS = {
    "files": frozenset({"file"}),
    "web": frozenset({"web"}),
    "automation": frozenset({"todo", "cronjob"}),
    "local_compute": frozenset({"code_execution", "terminal"}),
}


def select_toolsets_for_route(decision, configured_toolsets: Iterable[str]) -> tuple[str, ...]:
    configured = {str(x) for x in configured_toolsets if str(x)}
    selected = set(ALWAYS_ON_TOOLSETS) & configured

    for group in getattr(decision, "skill_groups", ()) or ():
        selected.update(ROUTE_TOOLSETS.get(str(group), ()))

    for capability in getattr(decision, "capabilities", ()) or ():
        selected.update(CAPABILITY_TOOLSETS.get(str(capability), ()))

    selected.intersection_update(configured)
    return tuple(sorted(selected))


SAFE_FALLBACK_TOOLSETS = frozenset({
    "companion_profile",
    "companion_memory",
    "proactive_companion",
    "memory",
    "session_search",
    "file",
    "web",
})


def select_safe_fallback_toolsets(configured_toolsets: Iterable[str]) -> tuple[str, ...]:
    # Conservative fallback for ambiguous turns.
    configured = {str(x) for x in configured_toolsets if str(x)}
    return tuple(sorted(configured & SAFE_FALLBACK_TOOLSETS))

def _classify(text: str, config: dict):
    client = build_default_router(
        config=config, timeout_seconds=_CLASSIFY_BUDGET_SECONDS,
    ).local_classifier
    return client.classify(text).validate()


def resolve_turn_toolsets(user_message, configured_toolsets: Iterable[str], config: dict) -> tuple[str, ...]:
    """Select tools only; the caller retains its already resolved main model."""
    configured = tuple(configured_toolsets)
    # Do not serialize structured messages, attachments, or context to the router.
    if user_message is not None and not isinstance(user_message, str):
        return select_safe_fallback_toolsets(configured)
    text = user_message or ""
    try:
        decision = route_by_rules(text)
        if decision is not None:
            return select_toolsets_for_route(decision, configured)
    except Exception:
        logger.warning("SELECTIVE_LOADING_V2 phase=rules_failed")
        return select_safe_fallback_toolsets(configured)

    if text.strip() and _classifier_slot.acquire(blocking=False):
        try:
            future = _classifier_pool.submit(_classify, text, config)
        except RuntimeError:
            _classifier_slot.release()
        else:
            future.add_done_callback(lambda _: _classifier_slot.release())
            try:
                decision = future.result(timeout=_CLASSIFY_BUDGET_SECONDS)
                if decision.source == "local_qwen" and decision.confidence >= _MIN_CLASSIFY_CONFIDENCE:
                    logger.info("SELECTIVE_LOADING_V2 phase=local_qwen intent=%s", decision.intent)
                    return select_toolsets_for_route(decision, configured)
            except Exception:
                # Errors may include model output; keep diagnostics content-free.
                future.cancel()
    logger.info("SELECTIVE_LOADING_V2 phase=safe_fallback")
    return select_safe_fallback_toolsets(configured)
