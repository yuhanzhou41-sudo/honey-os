from __future__ import annotations

from collections.abc import Iterable

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
    # Conservative v1 fallback for ambiguous turns.
    configured = {str(x) for x in configured_toolsets if str(x)}
    return tuple(sorted(configured & SAFE_FALLBACK_TOOLSETS))
