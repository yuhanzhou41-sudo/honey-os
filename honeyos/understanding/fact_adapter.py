"""Read-only adapter for metadata from the existing Cognitive fact store."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .contracts import (
    FactAuthority,
    MemoryKind,
    MemorySourceRef,
    PersonalFactRef,
    PrivacyLevel,
)

_SENSITIVE_PREDICATES = frozenset({
    "address", "birth_date", "birthday", "contact", "email", "government_id",
    "phone", "precise_location",
})
_PREDICATE = re.compile(r"[a-z][a-z0-9_.:-]{0,63}\Z")


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _metadata(value: object) -> dict[str, object]:
    try:
        loaded = json.loads(str(value or "{}"))
        return loaded if isinstance(loaded, dict) else {}
    except (TypeError, ValueError):
        return {}


class CognitiveFactResolver:
    """Resolve current native facts without selecting their value text.

    External facts fail closed because the current cognitive schema has no
    uniform retrieval/chat/analysis grant. A future source adapter may expose
    them only after validating the owning source's live permission contract.
    """

    source_system = "honeyos_cognitive_fact"

    def __init__(self, db_path: Path, *, owner: str, lane: str,
                 namespace: str = "personal"):
        self.db_path = Path(db_path)
        self.owner = owner
        self.lane = lane
        self.namespace = namespace

    def __call__(self, owner: str, system: str,
                 record_id: str) -> MemorySourceRef | None:
        fact = self.resolve_fact(owner, system, record_id)
        return fact.source if fact else None

    def resolve_fact(self, owner: str, system: str,
                     record_id: str) -> PersonalFactRef | None:
        if owner != self.owner or system != self.source_system:
            return None
        try:
            uri = self.db_path.resolve().as_uri() + "?mode=ro"
            with sqlite3.connect(uri, uri=True, timeout=0.01) as db:
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only=ON")
                row = db.execute("""
                    SELECT fact_id,subject,predicate,status,valid_from,valid_to,
                           confidence,derived_from_episode_id,memory_origin,
                           source_system,source_scope,source_key,
                           content_fingerprint,metadata_json,created_at,updated_at
                    FROM memory_facts WHERE fact_id=?
                """, (record_id,)).fetchone()
            if row is None or row["status"] != "current":
                return None
            if row["memory_origin"] != "native":
                return None
            predicate = str(row["predicate"] or "").strip().lower()
            if not _PREDICATE.fullmatch(predicate):
                return None
            valid_to = _parse_datetime(row["valid_to"])
            if valid_to and valid_to <= datetime.now(timezone.utc):
                return None
            metadata = _metadata(row["metadata_json"])
            privacy_raw = str(metadata.get("privacy_level") or "").lower()
            if predicate in _SENSITIVE_PREDICATES:
                privacy = PrivacyLevel.SENSITIVE
            elif privacy_raw in {item.value for item in PrivacyLevel}:
                privacy = PrivacyLevel(privacy_raw)
            else:
                privacy = PrivacyLevel.PRIVATE
            authority_raw = str(metadata.get("fact_authority") or "").lower()
            if authority_raw == FactAuthority.NATIVE_OBSERVED.value:
                authority = FactAuthority.NATIVE_OBSERVED
            else:
                authority = FactAuthority.SELF_REPORTED
            created_at = _parse_datetime(row["created_at"])
            revision = str(row["updated_at"] or row["content_fingerprint"])
            source = MemorySourceRef(
                source_system=self.source_system,
                source_record_id=str(row["fact_id"]), owner=owner,
                lane=self.lane, namespace=self.namespace, revision=revision,
                kind=(MemoryKind.IDENTITY_FACT if authority == FactAuthority.NATIVE_OBSERVED
                      else MemoryKind.SELF_REPORT),
                retrievable=True, chat_allowed=True, analysis_allowed=True,
                source_hash=str(row["content_fingerprint"]),
                created_at=created_at, valid_from=_parse_datetime(row["valid_from"]),
                valid_to=valid_to,
            )
            return PersonalFactRef(
                predicate=predicate,
                value_ref=f"cognitive:{row['fact_id']}:{row['content_fingerprint']}",
                source=source, authority=authority, privacy_level=privacy,
            )
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError):
            return None
