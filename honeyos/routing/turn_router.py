from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from typing import Protocol
from .local_qwen import LocalQwenRouterClient
from .models import MemoryRoute, RouteDecision
from .rules import route_by_rules

class RouterClassifier(Protocol):
    def classify(self, text: str) -> RouteDecision: ...

class TurnRouter:
    def __init__(self, local_classifier: RouterClassifier | None = None):
        self.local_classifier = local_classifier

    def route(self, text: str) -> RouteDecision:
        rule_decision = route_by_rules(text)
        if rule_decision is not None:
            return rule_decision.validate()

        if self.local_classifier is not None:
            try:
                return self.local_classifier.classify(text).validate()
            except Exception:
                pass

        # Fail closed for token cost: never "load all skills" on router failure.
        return RouteDecision(
            intent="other", complexity="medium",
            memory=MemoryRoute(mode="minimal"),
            skill_groups=(), capabilities=(),
            model_tier="standard", confidence=0.25,
            source="fallback",
            reasons=("local_router_unavailable_or_invalid",),
        ).validate()

def build_default_router(
    *, config: dict | None = None, timeout_seconds: float = 12.0,
) -> TurnRouter:
    from urllib.parse import urlsplit

    if config is None:
        from pathlib import Path
        import yaml

        path = Path.home() / ".honeyos" / "config.yaml"
        config = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}) if path.exists() else {}

    profiles = config.get("model_profiles") or {}
    for profile in profiles.values():
        if not isinstance(profile, dict):
            continue
        base_url = str(profile.get("base_url") or "").rstrip("/")
        model = str(profile.get("model") or "")
        address = urlsplit(base_url)
        if (
            address.scheme == "http"
            and address.hostname in {"127.0.0.1", "localhost", "::1"}
            and profile.get("api_mode") == "chat_completions"
            and "qwen" in model.lower()
        ):
            return TurnRouter(local_classifier=LocalQwenRouterClient(
                url=base_url + "/chat/completions",
                model=model,
                timeout_seconds=timeout_seconds,
                max_tokens=64,
            ))
    return TurnRouter(local_classifier=LocalQwenRouterClient(
        timeout_seconds=timeout_seconds, max_tokens=64,
    ))


def main() -> None:
    p = argparse.ArgumentParser(description="Preview HoneyOS cheap turn routing.")
    p.add_argument("message", nargs="+")
    p.add_argument("--rules-only", action="store_true")
    args = p.parse_args()
    router = TurnRouter(None) if args.rules_only else build_default_router()
    decision = router.route(" ".join(args.message))
    print(json.dumps(asdict(decision), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
