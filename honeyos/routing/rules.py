from __future__ import annotations

import re

from .models import MemoryRoute, RouteDecision

_SIMPLE_CHAT = {
    "你好", "你好呀", "嗨", "嗨嗨", "哈喽", "hello", "hi", "hey",
    "谢谢", "谢谢你", "感谢", "晚安", "早安", "早上好", "晚上好",
    "在吗", "哈哈", "哈哈哈", "ok", "okay", "好的", "好",
}

_RECALL_PATTERNS = (
    r"你还记得", r"你记得", r"还记得我们", r"之前我们",
    r"以前我们", r"上次我们", r"之前我说过", r"我以前说过",
)

_AUTOMATION_PATTERNS = (
    r"提醒我", r"记得提醒", r"到时候提醒", r"每(?:天|周|月)",
    r"定时", r"闹钟", r"remind me",
)

# ASCII-token boundaries are used instead of \b because Python's Unicode
# \w treats Chinese characters as word characters. So "这个PDF" would not
# match r"\bpdf\b".
_FILE_PATTERNS = (
    r"(?<![A-Za-z0-9_])pdf(?![A-Za-z0-9_])",
    r"(?<![A-Za-z0-9_])pptx?(?![A-Za-z0-9_])",
    r"(?<![A-Za-z0-9_])docx?(?![A-Za-z0-9_])",
    r"(?<![A-Za-z0-9_])csv(?![A-Za-z0-9_])",
    r"这个文件", r"这份文件", r"附件", r"上传的",
)

_CODING_PATTERNS = (
    r"traceback", r"报错", r"bug", r"代码",
    r"\.py(?![A-Za-z0-9_])",
    r"\.ts(?![A-Za-z0-9_])",
    r"\.tsx(?![A-Za-z0-9_])",
    r"git ", r"pytest", r"npm ", r"编译", r"调试",
)

_STUDY_PATTERNS = (
    r"复习", r"考试", r"学习计划", r"闪卡", r"抽题", r"番茄钟",
    r"课程", r"背诵",
)

_RESEARCH_PATTERNS = (
    r"论文", r"研究", r"文献", r"核验", r"比较.*方案",
    r"统计分析", r"实验设计", r"p.?值", r"SCI",
)

_SYSTEM_PATTERNS = (
    r"honeyos", r"wsl", r"systemd", r"gateway", r"localhost",
    r"本地模型", r"llama\.cpp",
)

def _fullmatch_simple(text: str) -> bool:
    normalized = re.sub(r"[！!。.?？~～\s]+", "", text.strip().lower())
    simple = {
        re.sub(r"[！!。.?？~～\s]+", "", item.lower())
        for item in _SIMPLE_CHAT
    }
    return normalized in simple

def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)

def _natural_recall_v3(text: str) -> bool:
    value = str(text or '').strip()
    patterns = (
        r'我之前说过', r'我以前说过', r'我之前提过', r'我以前提过',
        r'之前我说的', r'以前我说的', r'我们之前聊过', r'我们以前聊过',
        r'之前我们聊过', r'以前我们聊过', r'你还记得', r'你记得',
        r'我们之前为什么', r'我们以前为什么',
    )
    return any(re.search(p, value) for p in patterns)

def route_by_rules(text: str) -> RouteDecision | None:
    if _natural_recall_v3(text):
        return RouteDecision(
            intent='recall',
            complexity='medium',
            memory=MemoryRoute(
                mode='precision',
                domains=('user', 'timeline'),
                signal='none',
            ),
            skill_groups=('memory',),
            capabilities=(),
            model_tier='standard',
            confidence=0.96,
            source='rules',
        )

    raw = (text or "").strip()

    if not raw or _fullmatch_simple(raw):
        return RouteDecision(
            intent="chat",
            complexity="low",
            memory=MemoryRoute(mode="none"),
            skill_groups=(),
            capabilities=(),
            model_tier="local",
            confidence=1.0 if not raw else 0.99,
            source="rules",
            reasons=("empty_or_simple_social",),
        )

    if _matches_any(raw, _AUTOMATION_PATTERNS):
        return RouteDecision(
            intent="automation",
            complexity="low",
            memory=MemoryRoute(mode="minimal", signal="episodic_candidate"),
            skill_groups=("automation",),
            capabilities=("automation",),
            model_tier="standard",
            confidence=0.97,
            source="rules",
            reasons=("explicit_automation_request",),
        )

    if _matches_any(raw, _RECALL_PATTERNS):
        return RouteDecision(
            intent="recall",
            complexity="medium",
            memory=MemoryRoute(
                mode="precision",
                domains=("relationship", "project", "user"),
            ),
            skill_groups=("memory",),
            capabilities=(),
            model_tier="standard",
            confidence=0.95,
            source="rules",
            reasons=("explicit_recall_language",),
        )

    signals = []
    if _matches_any(raw, _FILE_PATTERNS):
        signals.append("files")
    if _matches_any(raw, _CODING_PATTERNS):
        signals.append("coding")
    if _matches_any(raw, _STUDY_PATTERNS):
        signals.append("study")
    if _matches_any(raw, _RESEARCH_PATTERNS):
        signals.append("research")
    if _matches_any(raw, _SYSTEM_PATTERNS):
        signals.append("system")

    signals = list(dict.fromkeys(signals))

    # More than one domain is intentionally ambiguous at the rule layer.
    if len(signals) != 1:
        return None

    domain = signals[0]

    if domain == "files":
        return RouteDecision(
            intent="files",
            complexity="medium",
            memory=MemoryRoute(mode="minimal"),
            skill_groups=("files",),
            capabilities=("files",),
            model_tier="standard",
            confidence=0.91,
            source="rules",
            reasons=("single_obvious_domain:files",),
        )

    if domain == "coding":
        return RouteDecision(
            intent="coding",
            complexity="medium",
            memory=MemoryRoute(mode="topic", domains=("project",)),
            skill_groups=("coding",),
            capabilities=("local_compute",),
            model_tier="strong",
            confidence=0.90,
            source="rules",
            reasons=("single_obvious_domain:coding",),
        )

    if domain == "study":
        return RouteDecision(
            intent="study",
            complexity="medium",
            memory=MemoryRoute(mode="topic", domains=("study", "user")),
            skill_groups=("study",),
            capabilities=(),
            model_tier="standard",
            confidence=0.90,
            source="rules",
            reasons=("single_obvious_domain:study",),
        )

    if domain == "research":
        return RouteDecision(
            intent="research",
            complexity="high",
            memory=MemoryRoute(mode="topic", domains=("project", "user")),
            skill_groups=("research",),
            capabilities=("web",),
            model_tier="strong",
            confidence=0.90,
            source="rules",
            reasons=("single_obvious_domain:research",),
        )

    if domain == "system":
        return RouteDecision(
            intent="system",
            complexity="medium",
            memory=MemoryRoute(mode="topic", domains=("project",)),
            skill_groups=("system",),
            capabilities=("local_compute",),
            model_tier="standard",
            confidence=0.90,
            source="rules",
            reasons=("single_obvious_domain:system",),
        )

    return None
