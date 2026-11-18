from contextlib import closing
from datetime import datetime, timedelta, timezone
import gc
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from honeyos.events.internal import chat_events, reminder_events, study_events
from honeyos.events.store import Event, EventLedger, Mode, Source


class EventLedgerTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "events.sqlite"
        self.now = datetime(2026, 11, 18, tzinfo=timezone.utc)
        self.ledger = EventLedger(self.path, clock=lambda: self.now)

    def grant(self, source=Source.CHAT, mode=Mode.READ):
        return self.ledger.grant("owner", "review", source, mode, self.now + timedelta(minutes=1))

    def test_internal_adapters_keep_provenance_and_exclude_content(self):
        message = dict(id=1, timestamp=self.now.timestamp(), role="user", content="secret chat")
        plan = SimpleNamespace(id="plan-1", tasks=[
            SimpleNamespace(id="task-1", updated_at=self.now, status=SimpleNamespace(value="completed")),
        ])
        job = dict(
            id="job-1", task_kind="fixed_reminder", created_at=self.now.isoformat(),
            last_run_at=self.now.isoformat(), reminder_text="secret reminder",
        )
        events = [
            *chat_events("session-1", [message, {**message, "id": 2, "active": False}]),
            *study_events(plan),
            *reminder_events([job, {**job, "id": "agent", "task_kind": "agent"}]),
        ]
        self.assertEqual(self.ledger.ingest(events), 4)
        self.now += timedelta(seconds=2)
        self.assertEqual(self.ledger.ingest(reversed(events)), 0)

        for event in events:
            self.grant(event.source)
            rows = self.ledger.read("owner", "review", event.source)
            row = next(row for row in rows if row["id"] == event.id)
            self.assertEqual(tuple(json.loads(row["source_ref"])), event.source_ref)
            self.assertEqual(row["kind"], event.kind)
            self.assertEqual(row["observed_at"], row["occurred_at"])
            self.assertNotIn("secret", json.dumps(row))

    def test_projects_from_existing_session_study_and_scheduler_stores(self):
        from honeyos.core.state import SessionDB
        from honeyos.scheduler.jobs import create_job, list_jobs, use_cron_store
        from honeyos.study.repository import StudyRepository
        from honeyos.study.service import StudyService

        # Existing Study connection contexts finalize on collection on Windows.
        self.addCleanup(gc.collect)
        home = self.path.parent
        with closing(SessionDB(home / "state.db")) as sessions:
            sessions.create_session("demo-session", "api_server")
            message_id = sessions.append_message("demo-session", "user", "private message")
            chat = list(chat_events("demo-session", sessions.get_messages("demo-session")))
        self.assertEqual(chat[0].source_ref, ("demo-session", str(message_id)))

        study = StudyService(StudyRepository(home))
        day = self.now.date().isoformat()
        plan = study.create_plan({"title": "private plan", "start_date": day, "end_date": day})
        updated = study.create_task(plan.id, {"title": "private task", "scheduled_date": day})
        tasks = list(study_events(study.get_plan(plan.id)))
        self.assertEqual(tasks[0].source_ref, (plan.id, updated.tasks[0].id))

        with use_cron_store(home):
            job = create_job(prompt="", schedule="10m", task_kind="fixed_reminder",
                             reminder_text="private reminder", deliver="local")
            reminders = list(reminder_events(list_jobs()))
        self.assertEqual(reminders[0].source_ref, (job["id"],))
        self.assertEqual(self.ledger.ingest([*chat, *tasks, *reminders]), 3)

    def test_grants_are_exact_audited_and_expire_or_revoke(self):
        self.grant(mode=Mode.BACKGROUND)
        with self.assertRaises(PermissionError):
            self.ledger.read("owner", "review", Source.CHAT)
        grant = self.grant()
        for subject, app_id, source in [
            ("visitor", "review", Source.CHAT),
            ("owner", "other", Source.CHAT),
            ("owner", "review", Source.STUDY),
        ]:
            with self.assertRaises(PermissionError):
                self.ledger.read(subject, app_id, source)
        self.assertEqual(self.ledger.read("owner", "review", Source.CHAT), [])
        with closing(sqlite3.connect(self.path)) as db:
            audit = db.execute("SELECT grant_id FROM access_audit ORDER BY id").fetchall()
        self.assertEqual(audit, [(None,)] * 4 + [(grant,)])
        self.ledger.revoke(grant)
        with self.assertRaises(PermissionError):
            self.ledger.read("owner", "review", Source.CHAT)
        self.grant()
        self.now += timedelta(minutes=1)
        with self.assertRaises(PermissionError):
            self.ledger.read("owner", "review", Source.CHAT)

    def test_withdrawal_persists_and_blocks_new_versions_of_same_source(self):
        event = Event(Source.STUDY, ("plan", "task"), "task.planned", self.now)
        self.ledger.ingest([event])
        self.grant(Source.STUDY)
        self.ledger.withdraw(event.source, event.source_ref)
        self.ledger = EventLedger(self.path, clock=lambda: self.now)
        self.assertEqual(self.ledger.read("owner", "review", Source.STUDY), [])
        self.assertEqual(self.ledger.ingest([
            Event(event.source, event.source_ref, "task.completed", self.now)
        ]), 0)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute("SELECT id FROM events").fetchall(), [(event.id,)])

    def test_invalid_batch_rolls_back(self):
        with self.assertRaises(ValueError):
            self.ledger.ingest([
                Event(Source.CHAT, ("session", "1"), "message.user", self.now),
                Event(Source.CHAT, ("session", "2"), "message.user", self.now.replace(tzinfo=None)),
            ])
        self.grant()
        self.assertEqual(self.ledger.read("owner", "review", Source.CHAT), [])

    def test_review_projects_only_with_grant_and_filters_chat_session(self):
        from unittest.mock import Mock

        def events():
            return [
                Event(Source.CHAT, ("s1", "1"), "message.user", self.now),
                Event(Source.CHAT, ("s2", "2"), "message.assistant", self.now),
            ]

        refresh = Mock(side_effect=events)
        with self.assertRaises(PermissionError):
            self.ledger.read("owner", "review", Source.CHAT, refresh=refresh)
        refresh.assert_not_called()
        self.grant()
        self.grant()
        rows = self.ledger.read("owner", "review", Source.CHAT, reference_root="s1", refresh=refresh)
        refresh.assert_called_once()
        self.assertEqual([json.loads(row["source_ref"]) for row in rows], [["s1", "1"]])
        self.ledger.revoke_source("owner", "review", Source.CHAT)
        with self.assertRaises(PermissionError):
            self.ledger.read("owner", "review", Source.CHAT, refresh=refresh)
        refresh.assert_called_once()
        review = self.ledger.review("owner", "review")
        self.assertEqual(review["grants"], [])
        self.assertEqual([item["allowed"] for item in review["audit"]], [0, 1, 0])


if __name__ == "__main__":
    unittest.main()
