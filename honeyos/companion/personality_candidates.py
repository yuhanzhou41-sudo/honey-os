"""Provisional personality-candidate persistence for HoneyOS companion mode.

G2.1B.1 is deliberately isolated from runtime prompt assembly and from the
authoritative companion profile writer. It records possible emerging traits,
supporting/contradicting evidence, and suppressions. It never writes
IDENTITY.md, RELATIONSHIP.md, SOUL.md, or companion_name.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_ALLOWED_LAYERS = {"relational_self", "stable_core"}
_ALLOWED_DIRECTIONS = {"add", "strengthen", "soften", "evolve"}
_ALLOWED_ORIGINS = {
    "self_observation",
    "assistant_behavior",
    "shared_experience",
    "self_reflection",
    "user_feedback",
}
_ALLOWED_EVIDENCE_TYPES = set(_ALLOWED_ORIGINS) | {"contradiction"}
_ALLOWED_STATUSES = {"candidate", "suppressed", "rejected", "promoted"}

_RESERVED_TRAIT_KEYS = {
    "name",
    "companion_name",
    "assistant_name",
    "display_name",
    "user_nickname",
    "relationship",
    "boundaries",
    "tool_permissions",
    "safety_policy",
    "credentials",
    "account_identity",
}

_FORBIDDEN_PAYLOAD_KEYS = set(_RESERVED_TRAIT_KEYS)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: object, *, field: str, limit: int) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} must not be empty")
    if len(text) > limit:
        raise ValueError(f"{field} exceeds {limit} characters")
    return text


def _normalize_trait_key(value: object) -> str:
    text = _clean_text(value, field="trait_key", limit=120).lower()
    normalized = "".join(ch if ch.isalnum() else "_" for ch in text)
    normalized = "_".join(part for part in normalized.split("_") if part)
    if not normalized:
        raise ValueError("trait_key must contain letters or digits")
    if normalized in _RESERVED_TRAIT_KEYS:
        raise ValueError(f"trait_key is outside personality formation: {normalized}")
    return normalized


def _validate_payload_keys(payload: Mapping[str, Any]) -> None:
    forbidden = sorted(set(payload) & _FORBIDDEN_PAYLOAD_KEYS)
    if forbidden:
        raise ValueError(
            "payload contains fields outside personality formation: "
            + ", ".join(forbidden)
        )


def _bounded_confidence(value: object) -> float:
    confidence = float(value)
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    return round(confidence, 6)


def _statement_fingerprint(statement: str) -> str:
    normalized = " ".join(statement.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PersonalityCandidate:
    candidate_id: str
    target_layer: str
    trait_key: str
    statement: str
    direction: str
    origin: str
    status: str
    confidence: float
    support_count: int
    contradiction_count: int
    first_seen_at: str
    last_seen_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PersonalityEvidence:
    evidence_id: str
    candidate_id: str
    evidence_type: str
    reference: str
    summary: str
    observed_at: str
    created_at: str


class PersonalityCandidateStore:
    """SQLite repository for provisional companion-personality candidates."""

    def __init__(self, home: Path | str, *, liked_only: bool = False):
        self.home = Path(home).expanduser().resolve()
        self.root = self.home / "companion"
        self.db_path = self.root / ("personality_liked_candidates.sqlite" if liked_only else "personality_candidates.sqlite")
        self.liked_only = liked_only
        self.audit_path = self.root / "personality_candidate_audit.jsonl"

    def _connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema(conn)
        return conn

    @staticmethod
    def _ensure_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS personality_candidates (
                candidate_id TEXT PRIMARY KEY,
                target_layer TEXT NOT NULL,
                trait_key TEXT NOT NULL,
                statement TEXT NOT NULL,
                direction TEXT NOT NULL,
                origin TEXT NOT NULL,
                status TEXT NOT NULL,
                confidence REAL NOT NULL,
                support_count INTEGER NOT NULL,
                contradiction_count INTEGER NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_personality_candidate_active_trait
                ON personality_candidates(target_layer, trait_key)
                WHERE status = 'candidate';

            CREATE TABLE IF NOT EXISTS personality_candidate_evidence (
                evidence_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                reference TEXT NOT NULL DEFAULT '',
                summary TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(candidate_id)
                    REFERENCES personality_candidates(candidate_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_personality_candidate_evidence_candidate
                ON personality_candidate_evidence(candidate_id, observed_at);

            CREATE TABLE IF NOT EXISTS personality_candidate_suppressions (
                suppression_id TEXT PRIMARY KEY,
                trait_key TEXT NOT NULL,
                statement_fingerprint TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                suppress_same_evidence INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_personality_candidate_suppressions_trait
                ON personality_candidate_suppressions(trait_key);

            CREATE TABLE IF NOT EXISTS personality_pending_observations (
                observation_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL DEFAULT '',
                user_reference TEXT NOT NULL DEFAULT '',
                assistant_reference TEXT NOT NULL DEFAULT '',
                observed_at TEXT NOT NULL,
                signal_flags TEXT NOT NULL DEFAULT '[]',
                user_excerpt TEXT NOT NULL DEFAULT '',
                assistant_excerpt TEXT NOT NULL DEFAULT '',
                processed_at TEXT,
                reflection_batch_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_personality_pending_observations_pending
                ON personality_pending_observations(processed_at, observed_at);
            """
        )
        conn.commit()

    @staticmethod
    def _row_candidate(row: sqlite3.Row | None) -> PersonalityCandidate | None:
        if row is None:
            return None
        return PersonalityCandidate(**dict(row))

    @staticmethod
    def _row_evidence(row: sqlite3.Row) -> PersonalityEvidence:
        return PersonalityEvidence(**dict(row))

    def _audit(self, event: str, payload: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        row = {"timestamp": _utcnow(), "event": event, **dict(payload)}
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def _is_suppressed(
        self,
        conn: sqlite3.Connection,
        *,
        trait_key: str,
        statement: str,
    ) -> bool:
        fp = _statement_fingerprint(statement)
        rows = conn.execute(
            """
            SELECT statement_fingerprint, suppress_same_evidence
            FROM personality_candidate_suppressions
            WHERE trait_key = ?
            """,
            (trait_key,),
        ).fetchall()
        for row in rows:
            if not int(row["suppress_same_evidence"]):
                return True
            stored = str(row["statement_fingerprint"] or "")
            if not stored or stored == fp:
                return True
        return False

    @staticmethod
    def _insert_evidence(
        conn: sqlite3.Connection,
        *,
        candidate_id: str,
        evidence_type: str,
        reference: str,
        summary: str,
        observed_at: str,
        created_at: str,
    ) -> str:
        evidence_id = uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO personality_candidate_evidence (
                evidence_id, candidate_id, evidence_type, reference,
                summary, observed_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                candidate_id,
                evidence_type,
                str(reference or "").strip()[:500],
                _clean_text(summary, field="evidence summary", limit=1200),
                observed_at,
                created_at,
            ),
        )
        return evidence_id

    @staticmethod
    def _evidence_reference_exists(
        conn: sqlite3.Connection,
        *,
        candidate_id: str,
        reference: str,
        evidence_type: str | None = None,
    ) -> bool:
        """True when this candidate already holds evidence from the same source.

        The reference is the stable observation id. Reflection batches may
        re-summarise the same observation, and a retry may replay a batch; the
        source event must never be counted as independent support twice.
        """
        value = str(reference or "").strip()[:500]
        if not value:
            return False
        sql = (
            "SELECT 1 FROM personality_candidate_evidence "
            "WHERE candidate_id = ? AND reference = ?"
        )
        params: list[object] = [candidate_id, value]
        if evidence_type is not None:
            sql += " AND evidence_type = ?"
            params.append(evidence_type)
        sql += " LIMIT 1"
        row = conn.execute(sql, params).fetchone()
        return row is not None

    def create_candidate(
        self,
        *,
        target_layer: str,
        trait_key: str,
        statement: str,
        direction: str = "add",
        origin: str = "self_observation",
        confidence: float = 0.5,
        evidence_summary: str | None = None,
        evidence_reference: str = "",
        observed_at: str | None = None,
        **extra: Any,
    ) -> PersonalityCandidate:
        _validate_payload_keys(extra)
        layer = _clean_text(target_layer, field="target_layer", limit=40)
        if layer not in _ALLOWED_LAYERS:
            raise ValueError(f"unsupported target_layer: {layer}")
        key = _normalize_trait_key(trait_key)
        statement_clean = _clean_text(statement, field="statement", limit=800)
        direction_clean = _clean_text(direction, field="direction", limit=40)
        if direction_clean not in _ALLOWED_DIRECTIONS:
            raise ValueError(f"unsupported direction: {direction_clean}")
        origin_clean = _clean_text(origin, field="origin", limit=60)
        if origin_clean not in _ALLOWED_ORIGINS:
            raise ValueError(f"unsupported origin: {origin_clean}")
        confidence_value = _bounded_confidence(confidence)
        now = _utcnow()
        observed = observed_at or now

        with self._connect() as conn:
            if self._is_suppressed(conn, trait_key=key, statement=statement_clean):
                raise ValueError("candidate is suppressed")

            existing_row = conn.execute(
                """
                SELECT * FROM personality_candidates
                WHERE target_layer = ? AND trait_key = ? AND status = 'candidate'
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (layer, key),
            ).fetchone()

            if existing_row is None:
                candidate_id = uuid.uuid4().hex
                support_count = 1 if evidence_summary else 0
                conn.execute(
                    """
                    INSERT INTO personality_candidates (
                        candidate_id, target_layer, trait_key, statement,
                        direction, origin, status, confidence,
                        support_count, contradiction_count,
                        first_seen_at, last_seen_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'candidate', ?, ?, 0, ?, ?, ?, ?)
                    """,
                    (
                        candidate_id,
                        layer,
                        key,
                        statement_clean,
                        direction_clean,
                        origin_clean,
                        confidence_value,
                        support_count,
                        observed,
                        observed,
                        now,
                        now,
                    ),
                )
                if evidence_summary:
                    self._insert_evidence(
                        conn,
                        candidate_id=candidate_id,
                        evidence_type=origin_clean,
                        reference=evidence_reference,
                        summary=evidence_summary,
                        observed_at=observed,
                        created_at=now,
                    )
                conn.commit()
                candidate = self.get_candidate(candidate_id)
                assert candidate is not None
                self._audit(
                    "candidate_created",
                    {
                        "candidate_id": candidate_id,
                        "target_layer": layer,
                        "trait_key": key,
                    },
                )
                return candidate

            existing = self._row_candidate(existing_row)
            assert existing is not None
            new_confidence = min(
                1.0,
                round(max(existing.confidence, confidence_value) + 0.05, 6),
            )
            support_increment = 1 if evidence_summary else 0
            duplicate_reference = bool(
                evidence_summary
                and self._evidence_reference_exists(
                    conn,
                    candidate_id=existing.candidate_id,
                    reference=evidence_reference,
                )
            )
            if duplicate_reference:
                support_increment = 0
                new_confidence = max(existing.confidence, confidence_value)
            conn.execute(
                """
                UPDATE personality_candidates
                SET statement = ?,
                    direction = ?,
                    origin = ?,
                    confidence = ?,
                    support_count = support_count + ?,
                    last_seen_at = ?,
                    updated_at = ?
                WHERE candidate_id = ?
                """,
                (
                    statement_clean,
                    direction_clean,
                    origin_clean,
                    new_confidence,
                    support_increment,
                    observed,
                    now,
                    existing.candidate_id,
                ),
            )
            if evidence_summary and not duplicate_reference:
                self._insert_evidence(
                    conn,
                    candidate_id=existing.candidate_id,
                    evidence_type=origin_clean,
                    reference=evidence_reference,
                    summary=evidence_summary,
                    observed_at=observed,
                    created_at=now,
                )
            conn.commit()
            candidate = self.get_candidate(existing.candidate_id)
            assert candidate is not None
            self._audit(
                "candidate_supported",
                {
                    "candidate_id": candidate.candidate_id,
                    "trait_key": candidate.trait_key,
                    "support_count": candidate.support_count,
                },
            )
            return candidate

    def add_evidence(
        self,
        candidate_id: str,
        *,
        evidence_type: str,
        summary: str,
        reference: str = "",
        observed_at: str | None = None,
    ) -> PersonalityCandidate:
        evidence_type_clean = _clean_text(
            evidence_type, field="evidence_type", limit=60
        )
        if evidence_type_clean not in (_ALLOWED_EVIDENCE_TYPES - {"contradiction"}):
            raise ValueError(f"unsupported evidence_type: {evidence_type_clean}")
        now = _utcnow()
        observed = observed_at or now

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM personality_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            candidate = self._row_candidate(row)
            if candidate is None:
                raise KeyError(candidate_id)
            if candidate.status != "candidate":
                raise ValueError(f"candidate status does not allow support: {candidate.status}")

            duplicate_reference = self._evidence_reference_exists(
                conn,
                candidate_id=candidate_id,
                reference=reference,
            )
            if duplicate_reference:
                conn.commit()
            else:
                self._insert_evidence(
                    conn,
                    candidate_id=candidate_id,
                    evidence_type=evidence_type_clean,
                    reference=reference,
                    summary=summary,
                    observed_at=observed,
                    created_at=now,
                )
                confidence = min(1.0, round(candidate.confidence + 0.05, 6))
                conn.execute(
                    """
                    UPDATE personality_candidates
                    SET support_count = support_count + 1,
                        confidence = ?,
                        last_seen_at = ?,
                        updated_at = ?
                    WHERE candidate_id = ?
                    """,
                    (confidence, observed, now, candidate_id),
                )
                conn.commit()

        updated = self.get_candidate(candidate_id)
        assert updated is not None
        if duplicate_reference:
            self._audit(
                "evidence_duplicate_skipped",
                {
                    "candidate_id": candidate_id,
                    "trait_key": updated.trait_key,
                    "reference": str(reference or "")[:200],
                },
            )
            return updated
        self._audit(
            "evidence_added",
            {
                "candidate_id": candidate_id,
                "trait_key": updated.trait_key,
                "support_count": updated.support_count,
            },
        )
        return updated

    def record_contradiction(
        self,
        candidate_id: str,
        *,
        summary: str,
        reference: str = "",
        observed_at: str | None = None,
    ) -> PersonalityCandidate:
        now = _utcnow()
        observed = observed_at or now

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM personality_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            candidate = self._row_candidate(row)
            if candidate is None:
                raise KeyError(candidate_id)
            if candidate.status != "candidate":
                raise ValueError(
                    f"candidate status does not allow contradiction: {candidate.status}"
                )

            duplicate_reference = self._evidence_reference_exists(
                conn,
                candidate_id=candidate_id,
                reference=reference,
                evidence_type="contradiction",
            )
            if duplicate_reference:
                conn.commit()
            else:
                self._insert_evidence(
                    conn,
                    candidate_id=candidate_id,
                    evidence_type="contradiction",
                    reference=reference,
                    summary=summary,
                    observed_at=observed,
                    created_at=now,
                )
                confidence = max(0.0, round(candidate.confidence - 0.05, 6))
                conn.execute(
                    """
                    UPDATE personality_candidates
                    SET contradiction_count = contradiction_count + 1,
                        confidence = ?,
                        last_seen_at = ?,
                        updated_at = ?
                    WHERE candidate_id = ?
                    """,
                    (confidence, observed, now, candidate_id),
                )
                conn.commit()

        updated = self.get_candidate(candidate_id)
        assert updated is not None
        if duplicate_reference:
            self._audit(
                "contradiction_duplicate_skipped",
                {
                    "candidate_id": candidate_id,
                    "trait_key": updated.trait_key,
                    "reference": str(reference or "")[:200],
                },
            )
            return updated
        self._audit(
            "contradiction_added",
            {
                "candidate_id": candidate_id,
                "trait_key": updated.trait_key,
                "contradiction_count": updated.contradiction_count,
            },
        )
        return updated

    def suppress_candidate(
        self,
        candidate_id: str,
        *,
        reason: str = "",
        suppress_same_evidence: bool = True,
    ) -> PersonalityCandidate:
        return self._close_candidate(
            candidate_id,
            status="suppressed",
            reason=reason,
            suppress_same_evidence=suppress_same_evidence,
        )

    def reject_candidate(
        self,
        candidate_id: str,
        *,
        reason: str = "",
        suppress_same_evidence: bool = True,
    ) -> PersonalityCandidate:
        return self._close_candidate(
            candidate_id,
            status="rejected",
            reason=reason,
            suppress_same_evidence=suppress_same_evidence,
        )

    def _close_candidate(
        self,
        candidate_id: str,
        *,
        status: str,
        reason: str,
        suppress_same_evidence: bool,
    ) -> PersonalityCandidate:
        if status not in {"suppressed", "rejected"}:
            raise ValueError(status)
        now = _utcnow()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM personality_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            candidate = self._row_candidate(row)
            if candidate is None:
                raise KeyError(candidate_id)

            conn.execute(
                """
                UPDATE personality_candidates
                SET status = ?, updated_at = ?
                WHERE candidate_id = ?
                """,
                (status, now, candidate_id),
            )
            conn.execute(
                """
                INSERT INTO personality_candidate_suppressions (
                    suppression_id, trait_key, statement_fingerprint,
                    reason, suppress_same_evidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    candidate.trait_key,
                    _statement_fingerprint(candidate.statement)
                    if suppress_same_evidence
                    else "",
                    str(reason or "").strip()[:800],
                    1 if suppress_same_evidence else 0,
                    now,
                ),
            )
            conn.commit()

        updated = self.get_candidate(candidate_id)
        assert updated is not None
        self._audit(
            f"candidate_{status}",
            {
                "candidate_id": candidate_id,
                "trait_key": candidate.trait_key,
                "reason": str(reason or "")[:300],
            },
        )
        return updated


    def capture_observation(
        self,
        *,
        session_id: str = "",
        user_reference: str = "",
        assistant_reference: str = "",
        observed_at: str | None = None,
        signal_flags: list[str] | tuple[str, ...] | None = None,
        user_excerpt: str = "",
        assistant_excerpt: str = "",
    ) -> str:
        """Record bounded, model-free observation material for later reflection."""
        now = _utcnow()
        observed = observed_at or now
        observation_id = uuid.uuid4().hex

        flags: list[str] = []
        for item in signal_flags or []:
            flag = str(item or "").strip()
            if flag and flag not in flags:
                flags.append(flag[:80])

        user_text = str(user_excerpt or "").strip()[:800]
        assistant_text = str(assistant_excerpt or "").strip()[:1200]
        session_value = str(session_id or "").strip()[:160]
        user_reference_value = str(user_reference or "").strip()[:200]
        assistant_reference_value = str(assistant_reference or "").strip()[:200]
        # One source event may surface as several reply rows (retries, model
        # switches). The stable identity is the originating user row when we
        # have one, otherwise the assistant row itself. Text is never used.
        dedupe_key = user_reference_value or assistant_reference_value

        with self._connect() as conn:
            if self.liked_only or (session_value and dedupe_key):
                conn.execute("BEGIN IMMEDIATE")
                duplicate = conn.execute(
                    "SELECT observation_id, reflection_batch_id FROM personality_pending_observations "
                    "WHERE session_id=? "
                    "AND COALESCE(NULLIF(user_reference,''), assistant_reference)=? "
                    "LIMIT 1",
                    (session_value, dedupe_key),
                ).fetchone()
                if duplicate is not None:
                    if self.liked_only and duplicate["reflection_batch_id"] == "feedback_unavailable":
                        conn.execute(
                            "UPDATE personality_pending_observations "
                            "SET processed_at=NULL, reflection_batch_id='' WHERE observation_id=?",
                            (duplicate["observation_id"],),
                        )
                    return str(duplicate["observation_id"])
            conn.execute(
                """
                INSERT INTO personality_pending_observations (
                    observation_id,
                    session_id,
                    user_reference,
                    assistant_reference,
                    observed_at,
                    signal_flags,
                    user_excerpt,
                    assistant_excerpt,
                    processed_at,
                    reflection_batch_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, '', ?)
                """,
                (
                    observation_id,
                    session_value,
                    user_reference_value,
                    assistant_reference_value,
                    observed,
                    json.dumps(flags, ensure_ascii=False),
                    user_text,
                    assistant_text,
                    now,
                ),
            )
            conn.commit()

        self._audit(
            "observation_captured",
            {"observation_id": observation_id, "signal_flags": flags},
        )
        return observation_id

    def list_pending_observations(
        self,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        limit_value = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM personality_pending_observations
                WHERE processed_at IS NULL
                ORDER BY observed_at, created_at, observation_id
                LIMIT ?
                """,
                (limit_value,),
            ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["signal_flags"] = json.loads(item.get("signal_flags") or "[]")
            except Exception:
                item["signal_flags"] = []
            results.append(item)
        return results

    def mark_observations_processed(
        self,
        observation_ids: list[str] | tuple[str, ...],
        *,
        reflection_batch_id: str,
        processed_at: str | None = None,
    ) -> int:
        ids = [str(x).strip() for x in observation_ids if str(x).strip()]
        if not ids:
            return 0

        batch = _clean_text(
            reflection_batch_id,
            field="reflection_batch_id",
            limit=160,
        )
        when = processed_at or _utcnow()
        placeholders = ",".join("?" for _ in ids)

        with self._connect() as conn:
            cursor = conn.execute(
                f"""
                UPDATE personality_pending_observations
                SET processed_at = ?,
                    reflection_batch_id = ?
                WHERE observation_id IN ({placeholders})
                  AND processed_at IS NULL
                """,
                (when, batch, *ids),
            )
            conn.commit()
            changed = int(cursor.rowcount or 0)

        if changed:
            self._audit(
                "observations_processed",
                {"reflection_batch_id": batch, "count": changed},
            )
        return changed

    def pending_observation_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM personality_pending_observations
                WHERE processed_at IS NULL
                """
            ).fetchone()
        return int(row["count"] if row is not None else 0)

    def get_candidate(self, candidate_id: str) -> PersonalityCandidate | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM personality_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        return self._row_candidate(row)

    def list_candidates(
        self,
        *,
        status: str | None = None,
        target_layer: str | None = None,
    ) -> list[PersonalityCandidate]:
        where: list[str] = []
        params: list[object] = []

        if status is not None:
            if status not in _ALLOWED_STATUSES:
                raise ValueError(f"unsupported status: {status}")
            where.append("status = ?")
            params.append(status)

        if target_layer is not None:
            if target_layer not in _ALLOWED_LAYERS:
                raise ValueError(f"unsupported target_layer: {target_layer}")
            where.append("target_layer = ?")
            params.append(target_layer)

        sql = "SELECT * FROM personality_candidates"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC, candidate_id"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_candidate(row) for row in rows if row is not None]

    def list_evidence(self, candidate_id: str) -> list[PersonalityEvidence]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM personality_candidate_evidence
                WHERE candidate_id = ?
                ORDER BY observed_at, created_at, evidence_id
                """,
                (candidate_id,),
            ).fetchall()
        return [self._row_evidence(row) for row in rows]


__all__ = [
    "PersonalityCandidate",
    "PersonalityCandidateStore",
    "PersonalityEvidence",
]
