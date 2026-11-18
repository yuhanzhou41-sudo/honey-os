from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from honeyos.companion.physiology_shadow import PhysiologyShadow, live_signals
from honeyos.companion.pre_reply_appraisal import appraise_before_reply, schedule_reply_appraisal
from honeyos.study import local_model


class AppraisalFallbackTest(unittest.TestCase):
    def appraise(self, home, **kwargs):
        return appraise_before_reply(
            home, "session", "turn", "The notes are gone.", recent=[], recalled="",
            now=datetime(2026, 11, 18, 10, tzinfo=timezone.utc), **kwargs,
        )

    def test_unconfigured_or_unavailable_model_does_not_retry(self):
        for error in (local_model.LocalStudyModelNotConfigured, local_model.LocalStudyModelUnavailable):
            with self.subTest(error=error), TemporaryDirectory() as home, patch.object(
                local_model, "generate_shadow_appraisal", side_effect=error,
            ) as generate:
                self.assertIsInstance(self.appraise(Path(home)), str)
                generate.assert_called_once()

    def test_cancel_before_request_and_discard_in_flight_result(self):
        with TemporaryDirectory() as home, patch.object(
            local_model, "generate_shadow_appraisal",
        ) as generate:
            root = Path(home)
            self.assertEqual(self.appraise(root, cancelled=lambda: True), "")
            generate.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

            cancelled = iter([False, True])
            with patch(
                "honeyos.companion.pre_reply_appraisal.PhysiologyShadow.apply_turn_appraisal"
            ) as apply:
                self.assertEqual(self.appraise(root, cancelled=lambda: next(cancelled)), "")
                apply.assert_not_called()
            generate.assert_called_once()

    def test_appraisal_has_its_own_socket_timeout(self):
        with patch.object(local_model, "_generate") as generate:
            local_model.generate_shadow_appraisal("system", "input")
            self.assertEqual(generate.call_args.kwargs["timeout"], 20)
            local_model.generate_flashcard_candidates("system", "input")
            self.assertNotIn("timeout", generate.call_args.kwargs)

    def test_completed_reply_schedules_state_update_without_waiting(self):
        started, release, finished = Event(), Event(), Event()
        profile = ContextVar("test_appraisal_profile", default=None)
        observed_profiles = []
        with TemporaryDirectory() as home:
            root = Path(home)

            def appraise():
                observed_profiles.append(profile.get())
                started.set()
                try:
                    if release.wait(timeout=5):
                        PhysiologyShadow(root).apply_turn_appraisal("s", "t", "surprise", 1)
                finally:
                    finished.set()

            token = profile.set("isolated")
            try:
                schedule_reply_appraisal(appraise, {"final_response": "Reply"})
            finally:
                profile.reset(token)
            try:
                self.assertTrue(started.wait(timeout=5))
                self.assertFalse(finished.is_set())
                self.assertEqual(live_signals(root), {})
            finally:
                release.set()
                self.assertTrue(finished.wait(timeout=5))
            self.assertGreater(live_signals(root)["epinephrine"], 0.05)
            self.assertEqual(observed_profiles, ["isolated"])

    def test_failed_or_interrupted_replies_do_not_queue_appraisal(self):
        with patch("honeyos.companion.pre_reply_appraisal._APPRAISAL_WORKER.submit") as submit:
            for result in [
                {"final_response": "", "failed": False},
                {"final_response": "Error", "failed": True},
                {"final_response": "Partial", "interrupted": True},
            ]:
                schedule_reply_appraisal(lambda: "", result)
            submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
