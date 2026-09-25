from honeyos.routing.models import MemoryRoute, RouteDecision
from honeyos.routing.rules import route_by_rules
from honeyos.routing.turn_router import TurnRouter

class ExplodingClassifier:
    def classify(self, text):
        raise AssertionError("local classifier should not be called")

class FakeClassifier:
    def __init__(self, decision):
        self.decision = decision
        self.calls = 0
    def classify(self, text):
        self.calls += 1
        return self.decision

class BrokenClassifier:
    def classify(self, text):
        raise RuntimeError("offline")

def test_greeting_uses_zero_skill_rule_path():
    d = TurnRouter(ExplodingClassifier()).route("你好")
    assert d.intent == "chat"
    assert d.memory.mode == "none"
    assert d.skill_groups == ()
    assert d.capabilities == ()
    assert d.model_tier == "local"
    assert d.source == "rules"

def test_thanks_uses_zero_skill_rule_path():
    d = TurnRouter(ExplodingClassifier()).route("谢谢你！")
    assert d.intent == "chat"
    assert d.skill_groups == ()
    assert d.memory.mode == "none"

def test_explicit_reminder_routes_only_automation():
    d = route_by_rules("提醒我晚上八点休息")
    assert d.intent == "automation"
    assert d.skill_groups == ("automation",)
    assert d.capabilities == ("automation",)

def test_explicit_recall_uses_precision_memory():
    d = route_by_rules("你还记得我们之前为什么放弃旧导入方案吗？")
    assert d.intent == "recall"
    assert d.memory.mode == "precision"
    assert d.skill_groups == ("memory",)

def test_single_file_domain_does_not_load_other_groups():
    d = route_by_rules("帮我看看这个PDF")
    assert d.skill_groups == ("files",)
    assert d.capabilities == ("files",)

def test_mixed_domain_request_goes_to_local_classifier():
    fake = FakeClassifier(RouteDecision(
        intent="research", complexity="high",
        memory=MemoryRoute(mode="topic", domains=("project",)),
        skill_groups=("files", "research"), capabilities=("files", "web"),
        model_tier="strong", confidence=0.9, source="local_qwen",
    ))
    d = TurnRouter(fake).route("分析这个PDF里的实验结果，再查文献比较一下")
    assert fake.calls == 1
    assert d.skill_groups == ("files", "research")

def test_ambiguous_request_uses_local_classifier():
    fake = FakeClassifier(RouteDecision(
        intent="other", complexity="medium", memory=MemoryRoute(mode="minimal"),
        skill_groups=(), capabilities=(), model_tier="standard",
        confidence=0.7, source="local_qwen",
    ))
    d = TurnRouter(fake).route("帮我处理一下这个事情")
    assert fake.calls == 1
    assert d.source == "local_qwen"

def test_local_failure_never_loads_all_skills():
    d = TurnRouter(BrokenClassifier()).route("这是一个非常模糊的请求")
    assert d.source == "fallback"
    assert d.skill_groups == ()
    assert d.capabilities == ()

def test_sentence_containing_hello_still_routes_coding():
    d = route_by_rules("你好，我想让你帮我检查这段代码为什么报错")
    assert d.intent == "coding"
    assert d.skill_groups == ("coding",)

def test_unknown_skill_group_causes_safe_fallback():
    bad = FakeClassifier(RouteDecision(
        intent="other", complexity="medium", memory=MemoryRoute(mode="minimal"),
        skill_groups=("everything",), capabilities=(), model_tier="standard",
        confidence=0.8, source="local_qwen",
    ))
    d = TurnRouter(bad).route("模糊请求")
    assert d.source == "fallback"
    assert d.skill_groups == ()

def test_memory_signal_is_candidate_only():
    fake = FakeClassifier(RouteDecision(
        intent="chat", complexity="low",
        memory=MemoryRoute(mode="minimal", signal="possible_preference"),
        skill_groups=(), capabilities=(), model_tier="standard",
        confidence=0.8, source="local_qwen",
    ))
    d = TurnRouter(fake).route("我最近好像更喜欢四十分钟专注")
    assert d.memory.signal == "possible_preference"

def test_honeyos_system_request():
    d = route_by_rules("HoneyOS gateway 好像没启动")
    assert d.intent == "system"
    assert d.skill_groups == ("system",)
    assert d.capabilities == ("local_compute",)
