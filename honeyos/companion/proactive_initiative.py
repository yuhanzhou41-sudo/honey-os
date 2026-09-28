
from __future__ import annotations

import hashlib
import inspect
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, get_args, get_origin

from honeyos.companion.momentary_state import load_momentary_state

from honeyos.companion.proactive_thought import build_proactive_thought_prompt
STATE_VERSION = 1
DEFAULT_SEED_COOLDOWN_HOURS = 6.0
# Curiosity alone should remain eligible after the normal idle window;
# the existing Topic Pool still owns consent, quiet-hours, daily limit,
# and minimum-interval delivery gates.
MIN_INITIATIVE_SCORE = 0.10

_INTERNAL_HOOK = build_proactive_thought_prompt()


@dataclass(frozen=True)
class InitiativeDecision:
    eligible: bool
    reason: str
    score: float
    idle_hours: float
    seed_cooldown_hours: float


def _now(value: datetime | None = None) -> datetime:
    result = value or datetime.now(timezone.utc)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _state_path(home: Path | str) -> Path:
    return Path(home).expanduser() / "companion" / "proactive_initiative_state.json"


def _load_seed_state(home: Path | str) -> dict[str, Any]:
    path = _state_path(home)
    if not path.exists():
        return {"version": STATE_VERSION, "last_seed_at": "", "last_signature": ""}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {"version": STATE_VERSION, "last_seed_at": "", "last_signature": ""}


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


def _preferences(store: Any) -> dict[str, Any]:
    try:
        payload = store.preferences_payload()
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def _latest_user_message_at(store: Any) -> datetime | None:
    try:
        channel = store.latest_channel()
    except Exception:
        return None
    if channel is None:
        return None
    if isinstance(channel, Mapping):
        return _parse_dt(channel.get("last_user_message_at"))
    return _parse_dt(getattr(channel, "last_user_message_at", None))


def _score_from_momentary_state(home: Path | str, now: datetime) -> float:
    state = load_momentary_state(home, now=now)
    axes = state.get("axes") if isinstance(state, Mapping) else {}
    if not isinstance(axes, Mapping):
        return 0.0

    def axis(name: str) -> float:
        try:
            return max(0.0, min(1.0, float(axes.get(name, 0.0) or 0.0)))
        except Exception:
            return 0.0

    score = (
        0.42 * axis("curiosity")
        + 0.22 * axis("reflectiveness")
        + 0.18 * axis("energy")
        + 0.14 * axis("positive_valence")
        + 0.10 * axis("warmth")
        + 0.08 * axis("playfulness")
        - 0.20 * axis("tension")
        - 0.18 * axis("negative_valence")
    )
    return max(0.0, min(1.0, score))


def evaluate_personal_initiative(
    home: Path | str,
    store: Any,
    *,
    now: datetime | None = None,
) -> InitiativeDecision:
    current = _now(now)
    prefs = _preferences(store)

    if not bool(prefs.get("consented")):
        return InitiativeDecision(False, "not_consented", 0.0, 0.0, 0.0)

    try:
        daily_limit = int(prefs.get("daily_limit", 0) or 0)
    except Exception:
        daily_limit = 0
    if daily_limit <= 0:
        return InitiativeDecision(False, "daily_limit_zero", 0.0, 0.0, 0.0)

    last_user = _latest_user_message_at(store)
    if last_user is None:
        return InitiativeDecision(False, "no_recent_owner_channel", 0.0, 0.0, 0.0)

    idle_hours = max(0.0, (current - last_user).total_seconds() / 3600.0)
    try:
        required_idle = max(0.0, float(prefs.get("idle_hours", 2.0) or 0.0))
    except Exception:
        required_idle = 2.0
    if idle_hours < required_idle:
        return InitiativeDecision(
            False, "owner_not_idle", 0.0, idle_hours, DEFAULT_SEED_COOLDOWN_HOURS
        )

    score = _score_from_momentary_state(home, current)
    if score < MIN_INITIATIVE_SCORE:
        return InitiativeDecision(
            False, "no_genuine_initiative_signal", score, idle_hours,
            DEFAULT_SEED_COOLDOWN_HOURS,
        )

    try:
        pref_interval = max(
            0.0, float(prefs.get("minimum_interval_hours", 0.0) or 0.0)
        )
    except Exception:
        pref_interval = 0.0
    cooldown = max(DEFAULT_SEED_COOLDOWN_HOURS, pref_interval)

    seed_state = _load_seed_state(home)
    last_seed = _parse_dt(seed_state.get("last_seed_at"))
    if last_seed is not None:
        elapsed = max(0.0, (current - last_seed).total_seconds() / 3600.0)
        if elapsed < cooldown:
            return InitiativeDecision(
                False, "initiative_seed_cooldown", score, idle_hours, cooldown
            )

    return InitiativeDecision(True, "eligible", score, idle_hours, cooldown)


def _fallback_for_required_parameter(name: str, annotation: Any, now: datetime) -> Any:
    lower = name.lower()
    if lower in {"id", "topic_id", "candidate_id"}:
        digest = hashlib.sha256(
            f"{now.isoformat()}|{_INTERNAL_HOOK}".encode("utf-8")
        ).hexdigest()[:16]
        return f"initiative-{digest}"
    if lower in {"title", "headline", "name"}:
        return "继续一个还值得说的想法"
    if lower in {"hook", "summary", "description", "content", "text", "body"}:
        return _INTERNAL_HOOK
    if lower in {"category", "topic_category", "kind"}:
        return "companion"
    if lower in {"source_url", "url", "link"}:
        return "honeyos://companion/initiative"
    if lower in {"source_name", "source_title", "source"}:
        return "HoneyOS companion initiative"
    if lower in {"selection_reason", "reason"}:
        return "momentary_state_continuity"
    if lower in {"published_at", "discovered_at", "created_at", "updated_at"}:
        return now
    if lower in {"score", "relevance_score", "priority", "quality_score"}:
        return 0.8
    if lower in {"language", "lang"}:
        return "zh"
    if lower in {"status"}:
        return "open"
    if lower in {"tags", "keywords", "categories"}:
        return ["companion", "continuity"]
    if lower in {"metadata", "extra", "properties"}:
        return {
            "internal": True,
            "initiative_kind": "relationship_continuity",
        }

    origin = get_origin(annotation)
    args = get_args(annotation)
    if annotation is bool:
        return False
    if annotation is int:
        return 0
    if annotation is float:
        return 0.0
    if annotation is str:
        return ""
    if origin in (list, tuple, set):
        return []
    if origin is dict:
        return {}
    if type(None) in args:
        return None
    return ""


def _build_topic_candidate(now: datetime) -> Any:
    """Build a TopicCandidate that satisfies TopicPoolStore.add_candidates()."""
    from datetime import timedelta
    from honeyos.companion.topic_pool import TopicCandidate

    source_id = hashlib.sha256(
        f"companion-initiative|{now.isoformat()}".encode("utf-8")
    ).hexdigest()[:20]
    source_url = "https://honeyos.local/companion/initiative/" + source_id

    return TopicCandidate(
        source_title="Companion continuity thought",
        source_url=source_url,
        source_name="HoneyOS companion initiative",
        summary=_INTERNAL_HOOK,
        hook=_INTERNAL_HOOK,
        category="companion",
        observed_at=now,
        expires_at=now + timedelta(hours=12),
        source_id=source_id,
        language="zh",
        published_at=None,
        score=0.8,
        selection_reason="momentary_state_continuity",
    )


def _insert_topic_candidate(store: Any, candidate: Any) -> Any:
    """Persist via the canonical TopicPoolStore.add_candidates() API."""
    return store.add_candidates([candidate])


def seed_personal_initiative_if_due(
    home: Path | str,
    store: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    decision = evaluate_personal_initiative(home, store, now=current)
    if not decision.eligible:
        return {
            "seeded": False,
            "reason": decision.reason,
            "score": decision.score,
            "idle_hours": decision.idle_hours,
        }

    candidate = _build_topic_candidate(current)
    result = _insert_topic_candidate(store, candidate)

    signature = hashlib.sha256(
        f"{current.date().isoformat()}|{decision.score:.3f}|{_INTERNAL_HOOK}".encode("utf-8")
    ).hexdigest()[:20]
    _atomic_write(
        _state_path(home),
        {
            "version": STATE_VERSION,
            "last_seed_at": current.isoformat(),
            "last_signature": signature,
            "last_score": round(decision.score, 6),
            "last_idle_hours": round(decision.idle_hours, 6),
        },
    )
    return {
        "seeded": True,
        "reason": "eligible",
        "score": decision.score,
        "idle_hours": decision.idle_hours,
        "insert_result": result,
    }
