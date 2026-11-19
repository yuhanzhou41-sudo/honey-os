"""Campus 考试快照：读取契约、导入替换与降级语义的单测（全部使用虚构数据）。"""
import json

import pytest

from honeyos.campus import CampusExamsService
from honeyos.campus.snapshot import InvalidSnapshotError, MissingSnapshotError, read_snapshot


def write_snapshot(path, rows=None, captured_at="2026-11-19T16:00:00+08:00",
                  source="https://jiaowu.cqmu.edu.cn:8080", schema="campus-exams-snapshot/1",
                  account=None):
    payload = {
        "schema": schema,
        "captured_at": captured_at,
        "source": source,
        "row_count": len(rows or []),
        "rows": rows or [],
    }
    if account is not None:
        payload["account"] = account
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def row(course, exam_date, arrangement="上午 09:00-11:00", location="教学楼 301"):
    return {"course": course, "exam_date": exam_date, "arrangement": arrangement, "location": location}


def test_refresh_reports_missing_snapshot(tmp_path):
    service = CampusExamsService(home=tmp_path, snapshot_path=tmp_path / "missing.json")
    result = service.refresh()
    assert result["result"] == "snapshot_missing"
    assert result["action"] == "open-host"


def test_refresh_imports_and_lists(tmp_path):
    snapshot = tmp_path / "exams.json"
    write_snapshot(snapshot, [
        row("外科学", "2026-11-25 09:00-11:00"),
        row("妇产科学", "时间未安排", arrangement="时间未安排", location="地点未安排"),
    ])
    service = CampusExamsService(home=tmp_path, snapshot_path=snapshot)
    result = service.refresh()
    assert result["result"] == "updated"
    assert result["imported"] == 2

    exams = service.get_exams()
    assert exams["has_data"] is True
    assert exams["needs_capture"] is False
    assert exams["row_count"] == 2
    assert exams["stale"] is False
    assert {r["course"] for r in exams["records"]} == {"外科学", "妇产科学"}


def test_refresh_replaces_previous_batch(tmp_path):
    snapshot = tmp_path / "exams.json"
    write_snapshot(snapshot, [row("外科学", "2026-11-25 09:00")])
    service = CampusExamsService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "updated"

    write_snapshot(
        snapshot,
        [row("内科学", "2026-12-02 14:00"), row("病理学", "2026-12-09 09:00")],
        captured_at="2026-11-19T18:00:00+08:00",
    )
    result = service.refresh()
    assert result["result"] == "updated"
    assert result["imported"] == 2
    assert {r["course"] for r in service.get_exams()["records"]} == {"内科学", "病理学"}


def test_older_snapshot_does_not_overwrite_newer(tmp_path):
    snapshot = tmp_path / "exams.json"
    write_snapshot(snapshot, [row("新课程", "2026-12-02 09:00")], captured_at="2026-11-19T18:00:00+08:00")
    service = CampusExamsService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "updated"

    write_snapshot(snapshot, [row("旧课程", "2026-11-01 09:00")], captured_at="2026-11-19T16:00:00+08:00")
    result = service.refresh()
    assert result["result"] == "no_new_snapshot"
    assert {r["course"] for r in service.get_exams()["records"]} == {"新课程"}


def test_invalid_schema_rejected(tmp_path):
    snapshot = tmp_path / "exams.json"
    write_snapshot(snapshot, schema="campus-exams-snapshot/0")
    service = CampusExamsService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "snapshot_invalid"
    with pytest.raises(InvalidSnapshotError):
        read_snapshot(snapshot)


def test_unparsable_captured_at_rejected(tmp_path):
    snapshot = tmp_path / "exams.json"
    write_snapshot(snapshot, [row("外科学", "2026-11-25 09:00")], captured_at="not-a-time")
    service = CampusExamsService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "snapshot_invalid"


def test_missing_snapshot_raises(tmp_path):
    with pytest.raises(MissingSnapshotError):
        read_snapshot(tmp_path / "nope.json")


def test_empty_rows_means_confirmed_no_exams(tmp_path):
    snapshot = tmp_path / "exams.json"
    write_snapshot(snapshot, [])
    service = CampusExamsService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "updated"
    exams = service.get_exams()
    assert exams["has_data"] is True
    assert exams["needs_capture"] is False
    assert exams["row_count"] == 0


def test_stale_flag_after_threshold(tmp_path):
    snapshot = tmp_path / "exams.json"
    write_snapshot(snapshot, [row("外科学", "2026-11-25 09:00")], captured_at="2026-11-17T10:00:00+08:00")
    service = CampusExamsService(home=tmp_path, snapshot_path=snapshot)
    service.refresh()
    assert service.get_exams()["stale"] is True


def test_accounts_do_not_overwrite_each_other(tmp_path):
    major = tmp_path / "major.json"
    minor = tmp_path / "minor.json"
    write_snapshot(major, [row("外科学", "2026-12-01 09:00")], account="major")
    write_snapshot(minor, [row("中医基础", "2026-12-02 09:00")], account="minor",
                   captured_at="2026-11-19T17:00:00+08:00")

    assert CampusExamsService(home=tmp_path, snapshot_path=major).refresh()["imported"] == 1
    assert CampusExamsService(home=tmp_path, snapshot_path=minor).refresh()["imported"] == 1

    major_rows = CampusExamsService(home=tmp_path, account="major").get_exams()
    minor_rows = CampusExamsService(home=tmp_path, account="minor").get_exams()
    assert [r["course"] for r in major_rows["records"]] == ["外科学"]
    assert [r["course"] for r in minor_rows["records"]] == ["中医基础"]
    assert major_rows["account"] == "major"


def test_snapshot_file_is_account_scoped():
    from honeyos.campus.snapshot import snapshot_file

    assert snapshot_file("default") == "exams.latest.json"
    assert snapshot_file("major") == "exams.major.latest.json"


def test_invalid_account_rejected(tmp_path):
    snapshot = tmp_path / "exams.json"
    write_snapshot(snapshot, [row("外科学", "2026-12-01 09:00")], account="../etc")
    service = CampusExamsService(home=tmp_path, snapshot_path=snapshot)
    assert service.refresh()["result"] == "snapshot_invalid"


def test_legacy_database_without_account_column_is_upgraded(tmp_path):
    import sqlite3

    db_dir = tmp_path / "campus"
    db_dir.mkdir(parents=True)
    conn = sqlite3.connect(db_dir / "campus.db")
    conn.executescript(
        """
        CREATE TABLE campus_exam_records (
            id TEXT PRIMARY KEY, source TEXT NOT NULL, batch_key TEXT NOT NULL,
            course TEXT NOT NULL, exam_date TEXT NOT NULL, arrangement TEXT NOT NULL,
            location TEXT NOT NULL, fingerprint TEXT NOT NULL, captured_at TEXT NOT NULL,
            created_at TEXT NOT NULL);
        CREATE TABLE campus_snapshot_meta (
            source TEXT PRIMARY KEY, batch_key TEXT NOT NULL, captured_at TEXT NOT NULL,
            row_count INTEGER NOT NULL, last_attempt_at TEXT NOT NULL,
            last_success_at TEXT NOT NULL);
        INSERT INTO campus_snapshot_meta VALUES
            ('https://jiaowu.cqmu.edu.cn:8080', '2026-11-19', '2026-11-19T10:00:00+08:00',
             0, '2026-11-19T10:00:00+08:00', '2026-11-19T10:00:00+08:00');
        """
    )
    conn.commit()
    conn.close()

    service = CampusExamsService(home=tmp_path)
    exams = service.get_exams()
    assert exams["account"] == "default"
    assert exams["has_data"] is True
