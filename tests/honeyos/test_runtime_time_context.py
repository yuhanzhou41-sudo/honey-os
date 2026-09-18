from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from honeyos.agent.turn_context import current_turn_time_context
from honeyos.core.time import (
    format_runtime_time_context,
    local_date,
    local_timezone,
    to_local,
)
from honeyos.scheduler import jobs
from honeyos.tools.cronjob_tools import CRONJOB_SCHEMA


CN = ZoneInfo("Asia/Shanghai")


def test_unified_local_clock_exposes_datetime_date_timezone_and_authority():
    current = datetime(2026, 9, 18, 20, 30, tzinfo=CN)

    with patch("honeyos.core.time.get_timezone", return_value=CN):
        note = format_runtime_time_context(current)

    assert local_timezone() is not None
    assert "Current local datetime: 2026-09-18T20:30:00+08:00" in note
    assert "Current local date: 2026-09-18" in note
    assert "Timezone: Asia/Shanghai (UTC+08:00)" in note
    assert "authoritative 'now' for this run" in note
    assert "今晚" in note and "明天" in note
    assert "start timestamps are historical metadata" in note


def test_unified_conversion_and_date_use_configured_timezone():
    utc_value = datetime.fromisoformat("2026-09-18T16:30:00+00:00")

    with patch("honeyos.core.time.get_timezone", return_value=CN):
        converted = to_local(utc_value)
        day = local_date(utc_value)

    assert converted.isoformat() == "2026-09-19T00:30:00+08:00"
    assert day.isoformat() == "2026-09-19"


def test_long_lived_session_refreshes_clock_across_midnight_each_turn():
    before_midnight = datetime(2026, 9, 18, 23, 59, 59, tzinfo=CN)
    after_midnight = datetime(2026, 9, 19, 0, 0, 1, tzinfo=CN)

    with (
        patch("honeyos.core.time.get_timezone", return_value=CN),
        patch("honeyos.core.time.now", side_effect=[before_midnight, after_midnight]),
    ):
        first_turn = current_turn_time_context()
        second_turn = current_turn_time_context()

    assert "Current local date: 2026-09-18" in first_turn
    assert "Current local date: 2026-09-19" in second_turn
    assert "2026-09-18T23:59:59+08:00" in first_turn
    assert "2026-09-19T00:00:01+08:00" in second_turn


def test_scheduler_uses_same_local_zone_for_naive_one_shot():
    current = datetime(2026, 9, 18, 18, 0, tzinfo=CN)

    with patch("honeyos.scheduler.jobs._honeyos_now", return_value=current):
        schedule = jobs.parse_schedule("2026-09-18T20:30:00")
        next_run = jobs.compute_next_run(schedule)

    assert schedule["run_at"] == "2026-09-18T20:30:00+08:00"
    assert next_run == "2026-09-18T20:30:00+08:00"


def test_cron_tool_forbids_using_session_start_as_current_date():
    description = CRONJOB_SCHEMA["parameters"]["properties"]["schedule"]["description"]

    assert "Runtime time context" in description
    assert "never use the conversation/session start date" in description
