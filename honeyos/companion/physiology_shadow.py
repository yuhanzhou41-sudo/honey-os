"""Persistent appraisal signals used in internal recall and initiative scoring."""
from __future__ import annotations

import json
import math
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from honeyos.core.time import local_timezone
from honeyos.companion.affect_evidence import assistant_self_clauses


@dataclass(frozen=True)
class Signal:
    baseline: float
    half_life_hours: float


@dataclass(frozen=True)
class TurnEvidence:
    context: str
    assistant: str
    timestamp: float | None = None


class AppraisalRejected(ValueError):
    pass


# Simulation parameters, not physiological measurements.
SIGNALS = {
    "cortisol": Signal(0.15, 2),
    "epinephrine": Signal(0.05, 0.15),
    "oxytocin": Signal(0.15, 5),
    "vasopressin": Signal(0.10, 4),
    "melatonin": Signal(0.10, 1),
    "dopamine": Signal(0.20, 0.75),
    "pge2": Signal(0.02, 3),
    "testosterone": Signal(0.15, 24),
    "estradiol": Signal(0.15, 24),
}

EFFECTS = {
    "unresolved_loss": {"cortisol": 0.22},
    "resolved_threat": {"cortisol": -0.22, "epinephrine": -0.08},
    "surprise": {"epinephrine": 0.32},
    "received_support": {"oxytocin": 0.18, "cortisol": -0.07},
    "relevant_social_change": {"vasopressin": 0.14},
    "unexpected_progress": {"dopamine": 0.20},
    "repeated_low_value_reward": {"dopamine": -0.12},
    "simulated_discomfort": {"pge2": 0.24},
    "simulated_recovery": {"pge2": -0.24},
    "sexual_interest": {"testosterone": 0.04, "estradiol": 0.02},
    "receptive_intimacy": {"estradiol": 0.04},
}

QWEN_EVENTS = frozenset({
    "unresolved_loss", "resolved_threat", "surprise", "received_support",
    "relevant_social_change", "unexpected_progress", "repeated_low_value_reward",
    "simulated_discomfort", "simulated_recovery", "sexual_interest", "receptive_intimacy",
})

_BODY_EVENT_EVIDENCE = {
    "simulated_discomfort": re.compile(r"模拟|想象|virtual|simulat|imaginar", re.I),
    "simulated_recovery": re.compile(r"模拟|想象|virtual|simulat|imaginar", re.I),
    "sexual_interest": re.compile(r"性唤起|性欲|性吸引|性方面|sex(?:ual)?|arous", re.I),
    "receptive_intimacy": re.compile(r"亲密|intimac|intimate", re.I),
}


def _instant(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("a timezone-aware timestamp is required")
    return value.astimezone(timezone.utc)


def _snapshot(row: sqlite3.Row | None, now: datetime) -> dict[str, float]:
    prior = json.loads(row["signals"]) if row else {}
    elapsed = max(0.0, (now.timestamp() - row["updated_at"]) / 3600) if row else 0
    values = {
        name: signal.baseline + (prior.get(name, signal.baseline) - signal.baseline)
        * 0.5 ** (elapsed / signal.half_life_hours)
        for name, signal in SIGNALS.items()
    }
    local = now.astimezone(local_timezone())
    hour = local.hour + local.minute / 60
    values["melatonin"] = 0.10 + 0.65 * max(0.0, math.cos(math.tau * (hour - 3) / 24))
    return values


def live_signals(home: Path | str, *, now: datetime | None = None) -> dict[str, float]:
    """Read the last validated state without creating a database in the hot path."""
    path = PhysiologyShadow(home).path.resolve()
    if not path.is_file():
        return {}
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.05)) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM physiology_state").fetchone()
        return _snapshot(row, _instant(now)) if row else {}
    except (OSError, sqlite3.Error, ValueError, TypeError):
        return {}


def _proposal(raw: object, allowed: frozenset[str], evidence: tuple[str, ...], original: str) -> tuple[str, float]:
    if not isinstance(raw, dict) or set(raw) != {"event", "strength", "quote"}:
        raise AppraisalRejected("invalid appraisal fields")
    event, strength, quote = raw["event"], raw["strength"], raw["quote"]
    if (
        not isinstance(event, str) or not isinstance(quote, str)
        or type(strength) not in (float, int) or not 0 <= strength <= 1
    ):
        raise AppraisalRejected("invalid appraisal values")
    if event == "none" and strength == 0 and not quote:
        return event, 0.0
    event_evidence = _BODY_EVENT_EVIDENCE.get(event)
    if event_evidence is not None and not event_evidence.search(quote):
        raise AppraisalRejected("appraisal lacks explicit first-person body or intimacy evidence")
    if (
        event not in allowed or not 4 <= len(quote.strip()) <= 180
        or quote not in original or not any(clause.startswith(quote) for clause in evidence)
    ):
        raise AppraisalRejected("appraisal lacks an allowed event and exact source evidence")
    return event, float(strength)


class PhysiologyShadow:
    """Keep only references and validated event types in the durable queue."""

    def __init__(self, home: Path | str):
        self.path = Path(home) / "companion" / "physiology_shadow.sqlite"

    def _open(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS physiology_state (
                id INTEGER PRIMARY KEY CHECK(id=1),
                updated_at REAL NOT NULL,
                signals TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS physiology_events (
                session_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                event TEXT,
                strength REAL,
                PRIMARY KEY(session_id, message_id)
            );
            CREATE TABLE IF NOT EXISTS physiology_turn_events (
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                event TEXT NOT NULL,
                PRIMARY KEY(session_id, turn_id)
            );
        """)
        return db

    def enqueue(self, session_id: str, message_id: int, *, now: datetime | None = None) -> bool:
        if not session_id.strip() or type(message_id) is not int or not 0 < message_id < 2**63:
            raise ValueError("a session and persisted assistant message ID are required")
        with closing(self._open()) as db, db:
            return db.execute(
                "INSERT OR IGNORE INTO physiology_events(session_id,message_id,created_at) VALUES (?,?,?)",
                (session_id, message_id, _instant(now).timestamp()),
            ).rowcount == 1

    def snapshot(self, *, now: datetime | None = None) -> dict[str, float]:
        with closing(self._open()) as db:
            return _snapshot(db.execute("SELECT * FROM physiology_state").fetchone(), _instant(now))

    @staticmethod
    def _apply_event(
        db: sqlite3.Connection, event: str, strength: float, current: datetime,
        source_time: float | None,
    ) -> dict[str, float]:
        prior = db.execute("SELECT * FROM physiology_state").fetchone()
        if prior and current.timestamp() < prior["updated_at"]:
            current = datetime.fromtimestamp(prior["updated_at"], timezone.utc)
        values = _snapshot(prior, current)
        if event == "none":
            return values
        elapsed = max(0.0, (current.timestamp() - source_time) / 3600) if source_time is not None else 0.0
        for name, delta in EFFECTS[event].items():
            if name == "cortisol" and delta > 0:
                delta *= 1 - 0.30 * values["oxytocin"]
            retained = 0.5 ** (elapsed / SIGNALS[name].half_life_hours)
            values[name] = max(0.0, min(1.0, values[name] + delta * strength * retained))
        db.execute(
            "INSERT INTO physiology_state VALUES (1,?,?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at,signals=excluded.signals",
            (current.timestamp(), json.dumps(values)),
        )
        return values

    def apply_turn_appraisal(
        self, session_id: str, turn_id: str, event: str, strength: float, *, now: datetime | None = None,
    ) -> dict[str, float]:
        """Apply one validated pre-reply event, including across request retries."""
        if not session_id or not turn_id or event not in QWEN_EVENTS | {"none"} or not 0 <= strength <= 1:
            raise ValueError("invalid pre-reply appraisal")
        timestamp = _instant(now)
        with closing(self._open()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            inserted = db.execute(
                "INSERT OR IGNORE INTO physiology_turn_events VALUES (?,?,?)",
                (session_id, turn_id, event),
            ).rowcount
            effective_event = event if inserted else "none"
            return self._apply_event(db, effective_event, strength, timestamp, source_time=None)

    def next_pending(self) -> tuple[str, int] | None:
        with closing(self._open()) as db:
            row = db.execute(
                "SELECT session_id,message_id FROM physiology_events WHERE status='pending' "
                "ORDER BY created_at,session_id,message_id LIMIT 1"
            ).fetchone()
        return (row["session_id"], row["message_id"]) if row else None

    def process_one(
        self,
        load_evidence: Callable[[str, int], TurnEvidence | None],
        evaluate: Callable[[str], object],
        *,
        allowed: frozenset[str] = QWEN_EVENTS,
        now: datetime | None = None,
        skip_rejected: bool = False,
    ) -> str:
        key = self.next_pending()
        if key is None:
            return "idle"
        evidence = load_evidence(*key)
        event, strength = ("none", 0.0)
        status = "applied" if evidence is not None else "withdrawn"
        own_clauses = assistant_self_clauses(evidence.assistant) if evidence is not None else ()
        if own_clauses:
            try:
                event, strength = _proposal(evaluate(evidence.context), allowed, own_clauses, evidence.assistant)
            except AppraisalRejected:
                if not skip_rejected:
                    raise
                status = "rejected"
            if load_evidence(*key) != evidence:
                status = "withdrawn"
                event, strength = ("none", 0.0)
        current = _instant(now)
        with closing(self._open()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            updated = db.execute(
                "UPDATE physiology_events SET status=?,event=?,strength=? "
                "WHERE session_id=? AND message_id=? AND status='pending'",
                (status, event, strength, *key),
            )
            if not updated.rowcount:
                return "already_processed"
            if event != "none":
                source_time = evidence.timestamp if evidence is not None else None
                self._apply_event(db, event, strength, current, source_time)
        return status
