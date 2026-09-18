from datetime import datetime, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from honeyos.companion.diary_automation import (
    build_diary_messages,
    message_local_time_for_date,
    next_generation_at,
)


def test_message_date_boundary_uses_configured_local_timezone():
    zone = ZoneInfo("Asia/Shanghai")
    before_midnight = datetime(2026, 9, 17, 15, 59, tzinfo=timezone.utc).timestamp()
    midnight = datetime(2026, 9, 17, 16, 0, tzinfo=timezone.utc).timestamp()

    included = message_local_time_for_date(
        before_midnight, target_date="2026-09-17", zone=zone
    )
    excluded = message_local_time_for_date(
        midnight, target_date="2026-09-17", zone=zone
    )

    assert included is not None
    assert included.isoformat(timespec="seconds") == "2026-09-17T23:59:00+08:00"
    assert excluded is None


def test_missing_invalid_and_naive_timestamps_are_excluded():
    zone = ZoneInfo("Asia/Shanghai")

    for value in (None, "", "not-a-date", "2026-09-17T20:00:00"):
        assert (
            message_local_time_for_date(
                value, target_date="2026-09-17", zone=zone
            )
            is None
        )


def test_scheduled_date_is_stable_even_if_execution_wakes_after_midnight():
    zone = ZoneInfo("Asia/Shanghai")
    planned_from = datetime(2026, 9, 17, 22, 32, tzinfo=zone)
    scheduled_at = next_generation_at(planned_from)
    simulated_wake = datetime(2026, 9, 18, 1, 59, tzinfo=zone)

    assert scheduled_at.isoformat() == "2026-09-17T23:30:00+08:00"
    assert simulated_wake.date() != scheduled_at.date()
    assert scheduled_at.date().isoformat() == "2026-09-17"


def test_prompt_declares_payload_date_as_only_today_boundary():
    zone = ZoneInfo("Asia/Shanghai")
    with patch("honeyos.core.time.get_timezone", return_value=zone):
        messages = build_diary_messages(
            target_date="2026-09-17",
            companion_profile={},
            user_entries=(),
            transcript=[
                {
                    "role": "user",
                    "content": "当天内容",
                    "timestamp": "2026-09-17T21:08:00+08:00",
                }
            ],
            current_time=datetime(2026, 9, 18, 0, 5, tzinfo=zone),
        )

    system = messages[0]["content"]
    assert "payload date" in system
    assert "timestamps are authoritative" in system
    assert "memories" in system
    assert "Current local datetime: 2026-09-18T00:05:00+08:00" in system
    assert "target date 2026-09-17" in system
    assert "conversation-start metadata" in system
    assert "2026-09-17T21:08:00+08:00" in messages[1]["content"]
