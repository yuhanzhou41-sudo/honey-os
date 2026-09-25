from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Intent = Literal[
    "chat", "recall", "study", "files", "coding", "research",
    "automation", "communication", "media", "system", "other",
]
Complexity = Literal["low", "medium", "high"]
MemoryMode = Literal["none", "minimal", "topic", "precision", "reminiscence"]
ModelTier = Literal["local", "standard", "strong"]
RouterSource = Literal["rules", "local_qwen", "fallback"]

_ALLOWED_INTENTS = {
    "chat", "recall", "study", "files", "coding", "research",
    "automation", "communication", "media", "system", "other",
}
_ALLOWED_COMPLEXITY = {"low", "medium", "high"}
_ALLOWED_MEMORY_MODES = {"none", "minimal", "topic", "precision", "reminiscence"}
_ALLOWED_MODEL_TIERS = {"local", "standard", "strong"}
_ALLOWED_SKILL_GROUPS = {
    "study", "files", "memory", "coding", "research",
    "communication", "automation", "media", "system",
}
_ALLOWED_CAPABILITIES = {
    "files", "web", "calendar", "email", "contacts",
    "github", "automation", "local_compute",
}
_ALLOWED_SIGNALS = {
    "none", "episodic_candidate", "possible_preference", "critical_candidate",
}

@dataclass(frozen=True)
class MemoryRoute:
    mode: MemoryMode = "minimal"
    domains: tuple[str, ...] = ()
    signal: Literal[
        "none", "episodic_candidate", "possible_preference", "critical_candidate",
    ] = "none"

@dataclass(frozen=True)
class RouteDecision:
    intent: Intent
    complexity: Complexity
    memory: MemoryRoute
    skill_groups: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    model_tier: ModelTier = "standard"
    confidence: float = 0.5
    source: RouterSource = "fallback"
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> "RouteDecision":
        if self.intent not in _ALLOWED_INTENTS:
            raise ValueError(f"invalid intent: {self.intent}")
        if self.complexity not in _ALLOWED_COMPLEXITY:
            raise ValueError(f"invalid complexity: {self.complexity}")
        if self.memory.mode not in _ALLOWED_MEMORY_MODES:
            raise ValueError(f"invalid memory mode: {self.memory.mode}")
        if self.memory.signal not in _ALLOWED_SIGNALS:
            raise ValueError(f"invalid memory signal: {self.memory.signal}")
        if self.model_tier not in _ALLOWED_MODEL_TIERS:
            raise ValueError(f"invalid model tier: {self.model_tier}")
        bad_groups = set(self.skill_groups) - _ALLOWED_SKILL_GROUPS
        if bad_groups:
            raise ValueError(f"invalid skill groups: {sorted(bad_groups)}")
        bad_caps = set(self.capabilities) - _ALLOWED_CAPABILITIES
        if bad_caps:
            raise ValueError(f"invalid capabilities: {sorted(bad_caps)}")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be in [0, 1]")
        return self
