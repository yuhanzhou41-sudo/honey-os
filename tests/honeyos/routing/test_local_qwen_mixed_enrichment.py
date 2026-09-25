from honeyos.routing.local_qwen import LocalQwenRouterClient

def test_mixed_pdf_research_enrichment():
    obj = {
        "intent": "research",
        "skill_groups": ["research"],
        "capabilities": ["web"],
    }
    out = LocalQwenRouterClient._enrich_compact_route(
        obj,
        "分析这个PDF里的实验结果，再查文献比较一下",
    )
    assert out["intent"] == "research"
    assert out["skill_groups"] == ["research", "files"]
    assert out["capabilities"] == ["web", "files"]

def test_file_only_enrichment():
    out = LocalQwenRouterClient._enrich_compact_route(
        {"intent": "files", "skill_groups": [], "capabilities": []},
        "帮我看看这个PPTX",
    )
    assert out["skill_groups"] == ["files"]
    assert out["capabilities"] == ["files"]

def test_research_only_enrichment():
    out = LocalQwenRouterClient._enrich_compact_route(
        {"intent": "other", "skill_groups": [], "capabilities": []},
        "帮我查文献比较一下",
    )
    assert out["intent"] == "research"
    assert out["skill_groups"] == ["research"]
    assert out["capabilities"] == ["web"]
