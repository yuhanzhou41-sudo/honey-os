from honeyos.routing.models import MemoryRoute, RouteDecision
from honeyos.routing.selective_loading import select_safe_fallback_toolsets, select_toolsets_for_route

CONFIGURED=("companion_profile","companion_memory","proactive_companion","memory","session_search","web","file","code_execution","terminal","todo","cronjob")

def test_local_qwen_research_can_narrow_to_web():
    d=RouteDecision(intent="research", complexity="high", memory=MemoryRoute(mode="topic"), skill_groups=("research",), capabilities=("web",), model_tier="strong", confidence=0.75, source="local_qwen").validate()
    selected=select_toolsets_for_route(d, CONFIGURED)
    assert "web" in selected
    assert "terminal" not in selected
    assert "code_execution" not in selected

def test_safe_fallback_preserves_v1_contract():
    selected=set(select_safe_fallback_toolsets(CONFIGURED))
    assert selected=={"companion_profile","companion_memory","proactive_companion","memory","session_search","file","web"}
