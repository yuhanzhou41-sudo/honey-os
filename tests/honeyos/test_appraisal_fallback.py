from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from honeyos.companion.pre_reply_appraisal import appraise_before_reply
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


if __name__ == "__main__":
    unittest.main()
