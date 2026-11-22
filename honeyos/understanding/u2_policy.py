"""Pure-program permission, signal extraction, and second-call gate."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .u2_contracts import EvidenceUnit, GateAction, GateDecision

TRIGGERS = frozenset({"preference", "pattern", "interaction", "style_value",
                      "conflict", "explicit_reassessment"})


@dataclass(frozen=True, slots=True)
class TriggerInput:
    enabled: bool
    completed: bool
    after_start: bool
    sources_allowed: bool
    namespace_allowed: bool
    suppressed: bool
    materially_new: bool
    call_issued: bool
    model_resolved: bool
    budget_ok: bool
    signals: frozenset[str]
    fact_only: bool = False
    chatter_only: bool = False


def decide_second_call(x: TriggerInput, *, evidence_refs: tuple[str, ...] = (),
                       label_refs: tuple[str, ...] = ()) -> GateDecision:
    checks = (
        (not x.enabled, "SKIP_DISABLED"),
        (not x.completed, "SKIP_NOT_COMPLETED"),
        (not x.after_start, "SKIP_BEFORE_START"),
        (not x.sources_allowed, "SKIP_UNAUTHORIZED"),
        (not x.namespace_allowed, "SKIP_NAMESPACE"),
        (x.suppressed, "SKIP_SUPPRESSED"),
        (not x.materially_new, "SKIP_DUPLICATE"),
        (x.call_issued, "SKIP_ALREADY_ISSUED"),
    )
    for failed, reason in checks:
        if failed:
            return GateDecision(GateAction.SKIP, reason)
    signals = sorted(x.signals & TRIGGERS)
    if not signals:
        reason = "SKIP_FACT_ONLY" if x.fact_only else (
            "SKIP_CHATTER" if x.chatter_only else "SKIP_NO_SIGNAL")
        return GateDecision(GateAction.SKIP, reason)
    reasons = tuple(f"RUN_{signal.upper()}" for signal in signals)
    if not x.model_resolved:
        return GateDecision(GateAction.BLOCKED, "BLOCKED_MODEL_UNRESOLVED",
                            all_reasons=reasons)
    if not x.budget_ok:
        return GateDecision(GateAction.DEFER, "DEFER_BUDGET", all_reasons=reasons)
    return GateDecision(GateAction.RUN, reasons[0], evidence_refs, label_refs, reasons)


_RULES = {
    "preference": re.compile(r"(?:我|本人).{0,10}(?:更喜欢|不喜欢|宁愿|更愿意|偏好)"),
    "pattern": re.compile(r"(?:我|本人).{0,14}(?:每次|经常|总是|反复|又).{0,18}(?:做|检查|准备|拖延|确认|复习)"),
    "interaction": re.compile(r"(?:和|跟).{1,16}(?:谈|沟通|说|解释|商量).{0,20}(?:我|想|担心|选择|准备)"),
    "style_value": re.compile(r"(?:我|本人).{0,12}(?:习惯|倾向|方式|取舍|看重|先).{1,28}(?:再|因为|而不是|比较)"),
    "conflict": re.compile(r"(?:以前|原来|过去).{0,24}(?:现在|但现在|如今)|(?:不是|不再).{0,12}(?:那样|这样)"),
    "explicit_reassessment": re.compile(r"(?:重新|再).{0,8}(?:评估|判断|理解).{0,12}(?:我|这个标签)"),
}
_CHATTER = re.compile(r"^(?:你好|嗨|晚安|早安|今天天气怎么样|谢谢)[！!。.？?]*$")
_FACT = re.compile(r"(?:学校是|考试(?:在|是)|周[一二三四五六日天]考试|是我(?:的)?同学|生日是)")


def extract_signals(evidence: tuple[EvidenceUnit, ...]) -> tuple[frozenset[str], bool, bool]:
    signals: set[str] = set()
    texts: list[str] = []
    for item in evidence:
        if "analysis" not in item.purposes or item.role != "user" or item.kind in {"fiction", "quote"}:
            continue
        text = unicodedata.normalize("NFKC", item.text).strip()
        texts.append(text)
        for name, rule in _RULES.items():
            if rule.search(text):
                signals.add(name)
    chatter = bool(texts) and all(_CHATTER.fullmatch(text) for text in texts)
    fact_only = bool(texts) and not signals and all(_FACT.search(text) for text in texts)
    return frozenset(signals), fact_only, chatter
