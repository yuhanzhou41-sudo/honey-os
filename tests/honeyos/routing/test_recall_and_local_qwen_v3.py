from pathlib import Path
import yaml
from honeyos.routing.rules import route_by_rules
from honeyos.routing.turn_router import build_default_router

CASES = [
    '我之前说过的国庆节计划是什么？',
    '我之前提过国庆节吗？',
    '之前我说的国庆安排是什么？',
    '我们之前聊过的国庆计划是什么？',
    '你记得我之前说过的国庆安排吗？',
    '你还记得国庆计划吗？',
    '我们之前为什么放弃旧记忆导入方案？',
]

def test_recall_variants():
    for text in CASES:
        d = route_by_rules(text)
        assert d is not None, text
        assert d.intent == 'recall', text
        assert d.skill_groups == ('memory',), text
        assert d.memory.mode == 'precision', text
        assert d.source == 'rules', text

def test_local_profile_reused():
    cfg = yaml.safe_load((Path.home()/'.honeyos'/'config.yaml').read_text(encoding='utf-8')) or {}
    expected = None
    for p in (cfg.get('model_profiles') or {}).values():
        if isinstance(p, dict) and '127.0.0.1:8080' in str(p.get('base_url') or '') and str(p.get('api_mode') or '') == 'chat_completions':
            expected = p
            break
    assert expected is not None
    c = build_default_router().local_classifier
    assert c.url == str(expected['base_url']).rstrip('/') + '/chat/completions'
    assert c.model == str(expected['model'])
    assert c.model != 'qwen3-4b-router'
    assert getattr(c, 'timeout_seconds') == 12.0
    assert c.max_tokens == 64
