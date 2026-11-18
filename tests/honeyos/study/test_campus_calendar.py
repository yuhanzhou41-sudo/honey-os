from datetime import date
from unittest.mock import Mock

import pytest

from honeyos.tools import cqmu_timetable


def test_campus_display_uses_detailed_view_and_preserves_confirmed_empty_days(monkeypatch):
    days = {"2026-11-19": ["内科学（1-2节）\n教学楼"], "2026-11-20": []}
    reader = Mock(return_value=days)
    monkeypatch.setattr(cqmu_timetable, "_read_calendar", reader)
    start, end = date(2026, 11, 19), date(2026, 11, 20)
    assert cqmu_timetable.read_campus_calendar(start, end) == {"days": days}
    reader.assert_called_once_with(start, end, detailed=True, interactive=False)
    reader.return_value = {"2026-11-21": ["课程"]}
    with pytest.raises(ValueError):
        cqmu_timetable.read_campus_calendar(start, end)
