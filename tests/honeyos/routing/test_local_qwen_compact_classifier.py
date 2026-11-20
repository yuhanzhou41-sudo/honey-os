from honeyos.routing.local_qwen import LocalQwenRouterClient, ROUTER_SYSTEM_PROMPT
from honeyos.routing.turn_router import build_default_router

def test_compact_prompt_is_small():
    assert len(ROUTER_SYSTEM_PROMPT) < 700
    assert "memory.signal" not in ROUTER_SYSTEM_PROMPT
    assert "model_tier" not in ROUTER_SYSTEM_PROMPT

def test_compact_parser_enriches_research():
    d = LocalQwenRouterClient._decision_from_object({
        "intent": "research",
        "skill_groups": ["files", "research"],
        "capabilities": ["files", "web"],
    })
    assert d.intent == "research"
    assert d.complexity == "high"
    assert d.memory.mode == "topic"
    assert d.skill_groups == ("files", "research")
    assert d.capabilities == ("files", "web")
    assert d.model_tier == "strong"
    assert d.source == "local_qwen"

def test_default_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME", str(tmp_path / ".honeyos"))
    c = build_default_router().local_classifier
    assert c.max_tokens == 64
    assert c.timeout_seconds == 12.0
