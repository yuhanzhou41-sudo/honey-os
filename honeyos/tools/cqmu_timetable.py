"""Read only the selected date range from an authenticated CQMU timetable tab."""
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess


def cqmu_date_range(start: object, end: object) -> tuple[date, date]:
    if not all(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
               for value in (start, end)):
        raise ValueError("请提供 YYYY-MM-DD 格式的开始和结束日期。")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if not 0 <= (last - first).days < 42:
        raise ValueError("请选择不超过 42 天且结束不早于开始的日期范围。")
    return first, last


def read_cqmu_timetable(start: date, end: date) -> dict:
    node = os.environ.get("HONEYOS_CQMU_EDGE_NODE")
    if not node or not Path(node).is_file():
        raise ValueError("课表浏览器连接未配置。请先打开本机验收 Edge。")
    script = Path(__file__).with_name("cqmu_timetable_reader.js").read_text(encoding="utf-8")
    result = subprocess.run(
        [node, "-e", script, start.isoformat(), end.isoformat()],
        capture_output=True, timeout=12, check=False, encoding="utf-8",
    )
    if result.returncode:
        raise ValueError("无法读取课表。请确认独立 Edge 已登录且只打开一张个人教学日历课表。")
    data = json.loads(result.stdout)
    if not isinstance(data, dict) or not data:
        raise ValueError("所选日期没有可确认的课表行。请核对学期和日期。")
    for day, periods in data.items():
        current, _ = cqmu_date_range(day, day)
        if (not start <= current <= end or not isinstance(periods, list)
                or any(type(period) is not int or not 1 <= period <= 18 for period in periods)
                or periods != sorted(set(periods))):
            raise ValueError("课表格式变化，请在浏览器里核对课表。")
    return {"start_date": start.isoformat(), "end_date": end.isoformat(),
            "occupied_periods": data, "missing_dates_are_unconfirmed": True}
