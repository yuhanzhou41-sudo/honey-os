"""Explicit event inspection from the profile owner's local settings."""

from datetime import datetime, timedelta
from itertools import islice

from honeyos.core.constants import get_honeyos_home

from .internal import chat_events, reminder_events, study_events
from .store import EventLedger, Mode, Source, UTC

_SUBJECT = "local-owner"
_APP = "honeyos-settings"


def _ledger():
    directory = get_honeyos_home() / "events"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return EventLedger(directory / "ledger.sqlite")


def _snapshot(source, session_id, session_db):
    if source == Source.CHAT:
        db = session_db()
        if db is not None:
            yield from chat_events(session_id, db.get_chat_event_rows(session_id))
    elif source == Source.STUDY:
        from honeyos.study.repository import StudyRepository

        for plan in StudyRepository().list_plans():
            yield from study_events(plan)
    else:
        from honeyos.scheduler.jobs import list_jobs

        yield from reminder_events(list_jobs(include_disabled=True))


def review_events(source, session_id, session_db):
    ledger = _ledger()
    events = []
    if source is not None:
        events = ledger.read(
            _SUBJECT, _APP, source, limit=30,
            reference_root=session_id if source == Source.CHAT else None,
            refresh=lambda: islice(_snapshot(source, session_id, session_db), 500),
        )
    return {**ledger.review(_SUBJECT, _APP), "events": events}


def change_event_grant(source, enabled):
    ledger = _ledger()
    if enabled:
        ledger.grant(_SUBJECT, _APP, source, Mode.READ, datetime.now(UTC) + timedelta(hours=1))
    else:
        ledger.revoke_source(_SUBJECT, _APP, source)
    return {**ledger.review(_SUBJECT, _APP), "events": []}
