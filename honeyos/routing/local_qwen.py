from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from .models import MemoryRoute, RouteDecision

DEFAULT_URL = os.getenv("HONEYOS_LOCAL_ROUTER_URL", "http://127.0.0.1:8080/v1/chat/completions")
DEFAULT_MODEL = os.getenv("HONEYOS_LOCAL_ROUTER_MODEL", "qwen3-4b-router")

ROUTER_SYSTEM_PROMPT = """Classify a HoneyOS user turn. Do not answer it. Return JSON only.\nRequired keys: intent, skill_groups, capabilities.\nintent: chat|recall|study|files|coding|research|automation|communication|media|system|other\nskill_groups: subset of study,files,memory,coding,research,communication,automation,media,system\ncapabilities: subset of files,web,calendar,email,contacts,github,automation,local_compute\nUse the fewest groups/capabilities needed. No prose, no markdown."""

@dataclass
class LocalQwenRouterClient:
    url: str = DEFAULT_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 8.0
    max_tokens: int = 220

    @staticmethod
    def _enrich_compact_route(obj: dict[str, Any], text: str) -> dict[str, Any]:
        value = str(text or '').lower()
        groups = list(obj.get('skill_groups') or [])
        caps = list(obj.get('capabilities') or [])

        file_markers = ('pdf', 'ppt', 'pptx', 'doc', 'docx', 'csv', '附件', '文件')
        research_markers = ('查文献', '文献', '检索', '搜索', '查资料', '研究', 'research', 'search')

        if any(m in value for m in file_markers):
            if 'files' not in groups:
                groups.append('files')
            if 'files' not in caps:
                caps.append('files')

        if any(m in value for m in research_markers):
            if 'research' not in groups:
                groups.append('research')
            if 'web' not in caps:
                caps.append('web')
            if obj.get('intent') in (None, '', 'other', 'files'):
                obj['intent'] = 'research'

        obj['skill_groups'] = groups
        obj['capabilities'] = caps
        return obj

    def classify(self, text: str) -> RouteDecision:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                {"role": "user", "content": str(text or "")[:1500]},
            ],
            "temperature": 0,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"local router unavailable: {exc}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except Exception as exc:
            raise RuntimeError("local router returned unexpected response") from exc
        obj = self._parse_json_object(content)
        if (
            not isinstance(obj.get("intent"), str) or not obj["intent"]
            or not all(
                isinstance(obj.get(key), list) and all(isinstance(item, str) for item in obj[key])
                for key in ("skill_groups", "capabilities")
            )
        ):
            raise RuntimeError("local router returned an invalid classification")
        obj = self._enrich_compact_route(obj, text[:1500])
        return self._decision_from_object(obj)

    @staticmethod
    def _parse_json_object(content: str) -> dict[str, Any]:
        text = (content or "").strip()
        if text.startswith("```"):
            text = text.replace("```json", "", 1).replace("```", "").strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start < 0 or end <= start:
                raise RuntimeError("local router did not return JSON")
            obj = json.loads(text[start:end + 1])
        if not isinstance(obj, dict):
            raise RuntimeError("local router JSON must be an object")
        return obj

    @staticmethod
    def _decision_from_object(obj: dict[str, Any]) -> RouteDecision:
        intent = str(obj.get("intent") or "other")
        defaults = {
            "chat": ("low", "none", (), "local"),
            "recall": ("medium", "precision", ("user", "timeline"), "standard"),
            "study": ("medium", "topic", ("study", "user"), "standard"),
            "files": ("medium", "minimal", (), "standard"),
            "coding": ("medium", "topic", ("project",), "strong"),
            "research": ("high", "topic", ("project", "user"), "strong"),
            "automation": ("low", "minimal", (), "standard"),
            "communication": ("medium", "minimal", (), "standard"),
            "media": ("medium", "minimal", (), "standard"),
            "system": ("medium", "topic", ("project",), "standard"),
            "other": ("medium", "minimal", (), "standard"),
        }
        complexity, memory_mode, memory_domains, model_tier = defaults.get(intent, defaults["other"])
        return RouteDecision(
            intent=intent,
            complexity=complexity,
            memory=MemoryRoute(mode=memory_mode, domains=memory_domains, signal="none"),
            skill_groups=tuple(dict.fromkeys(str(x) for x in (obj.get("skill_groups") or []) if str(x).strip())),
            capabilities=tuple(dict.fromkeys(str(x) for x in (obj.get("capabilities") or []) if str(x).strip())),
            model_tier=model_tier,
            confidence=float(obj.get("confidence", 0.75)),
            source="local_qwen",
            reasons=("local_qwen_compact_classifier",),
        ).validate()
