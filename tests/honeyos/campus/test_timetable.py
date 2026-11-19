"""Campus 课表快照：读取契约、导入替换与降级语义的单测（全部使用虚构数据）。"""
import json

import pytest

from honeyos.campus import CampusTimetableService
from honeyos.campus.snapshot import (
    InvalidSnapshotError,
    MissingSnapshotError,
    read_timetable_snapshot,
)


def write_snapshot(path, rows=None, captured_at="2026-11-19T16:00:00+08:00",
                  source="https://jiaowu.cqmu.edu.cn:8080",
                  schema="campus-timetable-snapshot/1"):
    payload = {
        "schema": schema,
        "captured_at": captured_at,
        "source": source,
        "row_count": len(rows or []),
        "rows": rows or [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def row(day="周一", period="1-2节", detail="系统解剖学 张老师 教学楼301"):
    return {"day": day, "period": period, "detail": detail}


def test_refresh_reports_missing_snapshot(tmp_path):
    service = CampusTimetableService(home=tmp_path, snapshot_path=tmp_path / "missing.json")
    result = service.refresh()
    assert result["result"] == "snapshot_missing"
    assert result["action"] == "open-host"


def test_refresh_imports_and_lists(tmp_path):
    snapshot = tmp_path / "timetable.json"
    write_snapshot(snapshot, [
        row("周一", "1-2节", "系统解剖学 张老师"),
        row("周三", "3-4节", "生理学 李老师"),
    ])
    service = CampusTimetableService(home=tmp_path, snapshot_path=snapshot)
    result = service.refresh()
    assert result["result"] == "updated"
    assert result["imported"] == 2

    timetable = service.get_timetable()
    assert timetable["has_data"] is True
    assert timetable["needs_capture"] is False
    assert timetable["row_count"] == 2
    assert timetable["stale"] is False
    assert {r["day"] for r in timetable["records"]} == {"周一", "周三"}


def test_refresh_replaces_previous_batch(tmp_path):
    snapshot = tmp_path / "timetable.json"
    write_snapshot(snapshot, [row("周一", "1-2节", "系统解剖学")])
    service = CampusTimetableService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "updated"

    write_snapshot(
        snapshot,
        [row("周二", "5-6节", "病理学"), row("周四", "7-8节", "药理学")],
        captured_at="2026-11-19T18:00:00+08:00",
    )
    result = service.refresh()
    assert result["result"] == "updated"
    assert result["imported"] == 2
    assert {r["day"] for r in service.get_timetable()["records"]} == {"周二", "周四"}


def test_older_snapshot_does_not_overwrite_newer(tmp_path):
    snapshot = tmp_path / "timetable.json"
    write_snapshot(snapshot, [row("周一", "1-2节", "新课程")],
                   captured_at="2026-11-19T18:00:00+08:00")
    service = CampusTimetableService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "updated"

    write_snapshot(snapshot, [row("周一", "1-2节", "旧课程")],
                   captured_at="2026-11-19T16:00:00+08:00")
    result = service.refresh()
    assert result["result"] == "no_new_snapshot"
    assert {r["detail"] for r in service.get_timetable()["records"]} == {"新课程"}


def test_invalid_schema_rejected(tmp_path):
    snapshot = tmp_path / "timetable.json"
    write_snapshot(snapshot, schema="campus-timetable-snapshot/0")
    service = CampusTimetableService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "snapshot_invalid"
    with pytest.raises(InvalidSnapshotError):
        read_timetable_snapshot(snapshot)


def test_blank_detail_rows_dropped(tmp_path):
    snapshot = tmp_path / "timetable.json"
    write_snapshot(snapshot, [row("周一", "1-2节", ""), row("周二", "3-4节", "病理学")])
    service = CampusTimetableService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["imported"] == 1


def test_missing_snapshot_raises(tmp_path):
    with pytest.raises(MissingSnapshotError):
        read_timetable_snapshot(tmp_path / "nope.json")


def test_empty_rows_means_confirmed_no_courses(tmp_path):
    snapshot = tmp_path / "timetable.json"
    write_snapshot(snapshot, [])
    service = CampusTimetableService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "updated"
    timetable = service.get_timetable()
    assert timetable["has_data"] is True
    assert timetable["needs_capture"] is False
    assert timetable["row_count"] == 0


def test_stale_flag_after_threshold(tmp_path):
    snapshot = tmp_path / "timetable.json"
    write_snapshot(snapshot, [row()], captured_at="2026-11-17T10:00:00+08:00")
    service = CampusTimetableService(home=tmp_path, snapshot_path=snapshot)
    service.refresh()
    assert service.get_timetable()["stale"] is True
