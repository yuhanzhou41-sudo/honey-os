
from __future__ import annotations

import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from honeyos.companion.affect_evidence import assistant_self_clauses

VERSION = 1
HALF_LIFE_HOURS = 3.0
HARD_EXPIRE_HOURS = 12.0
VISIBLE_THRESHOLD = 0.20

_AXES = (
    "curiosity",
    "reflectiveness",
    "seriousness",
    "warmth",
    "energy",
    "playfulness",
    "tension",
    "positive_valence",
    "negative_valence",
)

_PATTERNS = {
    "curiosity": [
        r"\bI(?:'m| am) curious\b",
        r"\bI wonder\b",
        r"\binteresting\b",
        r"我(?:(?:其实|真的|还|还是|有点|挺|很)\s*){0,4}好奇",
        r"我对[^。！？\n]{0,16}(?:有点|挺|很)?好奇",
        r"我想知道",
        r"挺有意思",
        r"很有意思",
    ],
    "reflectiveness": [
        r"\bI(?:'ve| have) noticed\b",
        r"\bI realize\b",
        r"\bI think\b",
        r"我发现",
        r"我意识到",
        r"我在想",
        r"我觉得",
    ],
    "seriousness": [
        r"\bseriously\b",
        r"\bimportant point\b",
        r"这点(?:很|比较)?重要",
        r"认真(?:地|来说|一点)",
        r"需要认真",
    ],
    "warmth": [
        r"\bI'm glad\b",
        r"\bI am glad\b",
        r"\bI like (?:that|this)\b",
        r"我(?:其实|真的|挺|很)?喜欢",
        r"我很高兴",
        r"我挺高兴",
    ],
    "energy": [
        r"\bI'm excited\b",
        r"\bI am excited\b",
        r"\bexciting\b",
        r"我(?:有点|挺|很)?兴奋",
        r"我突然想到",
    ],
    "playfulness": [
        r"哈哈",
        r"\bhaha\b",
        r"\bjoking\b",
        r"开个玩笑",
        r"有点好笑",
    ],
    "tension": [
        r"\bI disagree\b",
        r"\bI don't agree\b",
        r"\bI do not agree\b",
        r"我不认同",
        r"我不同意",
        r"我不这么看",
        r"我有点不舒服",
        r"我有点烦",
    ],
    "positive_valence": [
        r"\bI'm happy\b",
        r"\bI am happy\b",
        r"\bI'm glad\b",
        r"\bI am glad\b",
        r"我很开心",
        r"我挺开心",
        r"我很高兴",
        r"我挺高兴",
    ],
    "negative_valence": [
        r"\bI'm annoyed\b",
        r"\bI am annoyed\b",
        r"\bI'm frustrated\b",
        r"\bI am frustrated\b",
        r"我有点生气",
        r"我有点烦",
        r"我有点难受",
        r"我不太舒服",
    ],
}

_DELTAS = {
    "curiosity": 0.45,
    "reflectiveness": 0.35,
    "seriousness": 0.35,
    "warmth": 0.30,
    "energy": 0.35,
    "playfulness": 0.35,
    "tension": 0.30,
    "positive_valence": 0.35,
    "negative_valence": 0.35,
}


def _now(now: datetime | None = None) -> datetime:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


def _state_path(home: Path | str) -> Path:
    return Path(home).expanduser() / "companion" / "momentary_state.json"


def _neutral_state(now: datetime | None = None) -> dict[str, Any]:
    ts = _now(now)
    return {
        "version": VERSION,
        "updated_at": ts.isoformat(),
        "last_turn_id": "",
        "axes": {axis: 0.0 for axis in _AXES},
    }


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        content = value.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, Mapping):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(parts)
    return str(value or "")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _matched_axes(text: str) -> set[str]:
    matched: set[str] = set()
    if not text.strip():
        return matched
    self_text = "\n".join(assistant_self_clauses(text))
    for axis, patterns in _PATTERNS.items():
        for pattern in patterns:
            evidence = self_text if axis in {"warmth", "tension", "positive_valence", "negative_valence"} else text
            if re.search(pattern, evidence, re.IGNORECASE):
                matched.add(axis)
                break
    return matched


def load_momentary_state(
    home: Path | str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    path = _state_path(home)
    if not path.exists():
        return _neutral_state(current)

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        axes = raw.get("axes") if isinstance(raw, dict) else None
        if not isinstance(axes, dict):
            return _neutral_state(current)
        updated = datetime.fromisoformat(str(raw.get("updated_at") or ""))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
    except Exception:
        return _neutral_state(current)

    elapsed_hours = max(
        0.0,
        (current - updated).total_seconds() / 3600.0,
    )
    if elapsed_hours >= HARD_EXPIRE_HOURS:
        return _neutral_state(current)

    decay = math.pow(0.5, elapsed_hours / HALF_LIFE_HOURS)
    result = _neutral_state(current)
    result["last_turn_id"] = str(raw.get("last_turn_id") or "")
    result["source_updated_at"] = updated.isoformat()
    for axis in _AXES:
        try:
            result["axes"][axis] = _clamp(float(axes.get(axis, 0.0)) * decay)
        except Exception:
            result["axes"][axis] = 0.0
    return result


def update_momentary_state_from_turn(
    home: Path | str,
    *,
    assistant_response: Any,
    turn_id: Any = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    text = _coerce_text(assistant_response)
    matched = _matched_axes(text)
    previous = load_momentary_state(home, now=current)

    if not matched and max(previous["axes"].values(), default=0.0) < 0.01:
        return previous

    axes = dict(previous["axes"])
    for axis in matched:
        axes[axis] = _clamp(axes.get(axis, 0.0) + _DELTAS[axis])

    if "positive_valence" in matched:
        axes["negative_valence"] *= 0.55
        axes["tension"] *= 0.80
    if "negative_valence" in matched:
        axes["positive_valence"] *= 0.55
        axes["playfulness"] *= 0.75
    if "playfulness" in matched:
        axes["seriousness"] *= 0.75
        axes["tension"] *= 0.75
    if "seriousness" in matched:
        axes["playfulness"] *= 0.80

    state = {
        "version": VERSION,
        "updated_at": current.isoformat(),
        "last_turn_id": str(turn_id or ""),
        "axes": {axis: round(_clamp(axes.get(axis, 0.0)), 6) for axis in _AXES},
    }
    _atomic_write(_state_path(home), state)
    return state


def _active_labels(state: Mapping[str, Any]) -> list[str]:
    axes = state.get("axes") if isinstance(state, Mapping) else {}
    if not isinstance(axes, Mapping):
        return []

    labels = []
    mapping = [
        ("curiosity", "curious"),
        ("reflectiveness", "reflective"),
        ("seriousness", "serious"),
        ("warmth", "warm"),
        ("energy", "energized"),
        ("playfulness", "playful"),
        ("tension", "slightly tense"),
        ("positive_valence", "in a positive mood"),
        ("negative_valence", "in a somewhat negative mood"),
    ]
    for axis, label in mapping:
        try:
            if float(axes.get(axis, 0.0)) >= VISIBLE_THRESHOLD:
                labels.append(label)
        except Exception:
            continue
    return labels


def momentary_state_note(
    home: Path | str,
    *,
    now: datetime | None = None,
) -> str:
    state = load_momentary_state(home, now=now)
    labels = _active_labels(state)
    if not labels:
        return ""
    return (
        "Momentary companion state (temporary): "
        + ", ".join(labels)
        + ". Let this subtly color tone and initiative; do not announce or explain "
          "the state unless it arises naturally."
    )
