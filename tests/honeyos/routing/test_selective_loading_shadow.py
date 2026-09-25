from honeyos.routing.models import MemoryRoute, RouteDecision
from honeyos.routing.selective_loading import (
    select_safe_fallback_toolsets,
    select_toolsets_for_route,
)

CONFIGURED = (
    "companion_profile",
    "companion_memory",
    "proactive_companion",
    "memory",
    "session_search",
    "web",
    "file",
    "code_execution",
    "terminal",
    "skills",
    "todo",
    "cronjob",
    "vision",
    "tts",
    "image_gen",
)


def decision(*, groups=(), caps=(), intent="other"):
    return RouteDecision(
        intent=intent,
        complexity="medium",
        memory=MemoryRoute(mode="minimal"),
        skill_groups=tuple(groups),
        capabilities=tuple(caps),
        model_tier="standard",
        confidence=0.9,
        source="rules",
    ).validate()


def test_chat_keeps_only_semantic_companion_toolsets():
    selected = select_toolsets_for_route(decision(intent="chat"), CONFIGURED)
    assert selected == (
        "companion_memory",
        "companion_profile",
        "proactive_companion",
    )


def test_mixed_files_research_selects_file_and_web():
    selected = select_toolsets_for_route(
        decision(groups=("files", "research"), caps=("files", "web"), intent="research"),
        CONFIGURED,
    )
    assert "file" in selected
    assert "web" in selected
    assert "terminal" not in selected


def test_coding_selects_compute_and_file():
    selected = select_toolsets_for_route(
        decision(groups=("coding",), caps=("local_compute",), intent="coding"),
        CONFIGURED,
    )
    assert {"code_execution", "terminal", "file"} <= set(selected)


def test_never_invents_unconfigured_toolsets():
    configured = ("companion_profile", "web")
    selected = select_toolsets_for_route(
        decision(groups=("coding", "research"), caps=("web", "local_compute")),
        configured,
    )
    assert set(selected) == {"companion_profile", "web"}


def test_router_failure_does_not_fall_back_to_all_tools():
    selected = select_toolsets_for_route(decision(), CONFIGURED)
    assert set(selected) == {
        "companion_profile",
        "companion_memory",
        "proactive_companion",
    }


def test_safe_fallback_preserves_common_ambiguous_capabilities_only():
    selected = select_safe_fallback_toolsets(CONFIGURED)
    assert set(selected) == {
        "companion_profile", "companion_memory", "proactive_companion",
        "memory", "session_search", "file", "web",
    }
    assert "terminal" not in selected
    assert "code_execution" not in selected
    assert "cronjob" not in selected
    assert "vision" not in selected


def test_safe_fallback_never_invents_unconfigured_toolsets():
    selected = select_safe_fallback_toolsets(("companion_profile", "web"))
    assert selected == ("companion_profile", "web")
