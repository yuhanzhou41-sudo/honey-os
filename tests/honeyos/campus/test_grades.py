import json

from honeyos.campus import CampusGradesService


def row(course, score, credit="", term=""):
    return {"course": course, "score": score, "credit": credit, "term": term}


def write_snapshot(path, rows=None, captured_at="2026-11-19T20:00:00+08:00",
                   source="https://jiaowu.cqmu.edu.cn:8080",
                   schema="campus-grades-snapshot/1", account=None):
    payload = {
        "schema": schema,
        "captured_at": captured_at,
        "source": source,
        "rows": rows or [],
    }
    if account is not None:
        payload["account"] = account
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_missing_snapshot_returns_action(tmp_path):
    service = CampusGradesService(home=tmp_path, snapshot_path=tmp_path / "none.json")
    result = service.refresh()
    assert result["result"] == "snapshot_missing"
    assert result["action"] == "open-host"


def test_import_and_list(tmp_path):
    snapshot = tmp_path / "grades.json"
    write_snapshot(snapshot, [row("内科学", "88", "4", "2025-2026学年1学期")])
    service = CampusGradesService(home=tmp_path, snapshot_path=snapshot)

    result = service.refresh()
    assert result["result"] == "updated"
    assert result["imported"] == 1
    assert result["row_count"] == 1
    assert result["records"][0]["score"] == "88"


def test_old_snapshot_does_not_override(tmp_path):
    snapshot = tmp_path / "grades.json"
    write_snapshot(snapshot, [row("内科学", "88")], captured_at="2026-11-19T12:00:00+08:00")
    CampusGradesService(home=tmp_path, snapshot_path=snapshot).refresh()

    write_snapshot(snapshot, [row("内科学", "60")], captured_at="2026-11-19T11:00:00+08:00")
    result = CampusGradesService(home=tmp_path, snapshot_path=snapshot).refresh()

    assert result["result"] == "no_new_snapshot"
    assert CampusGradesService(home=tmp_path).get_grades()["records"][0]["score"] == "88"


def test_batch_replace(tmp_path):
    snapshot = tmp_path / "grades.json"
    write_snapshot(snapshot, [row("内科学", "88"), row("外科学", "91")])
    CampusGradesService(home=tmp_path, snapshot_path=snapshot).refresh()

    write_snapshot(snapshot, [row("外科学", "91")], captured_at="2026-11-19T21:00:00+08:00")
    result = CampusGradesService(home=tmp_path, snapshot_path=snapshot).refresh()

    assert result["row_count"] == 1
    assert result["records"][0]["course"] == "外科学"


def test_rows_without_course_are_dropped(tmp_path):
    snapshot = tmp_path / "grades.json"
    write_snapshot(snapshot, [row("", "99"), row("内科学", "88")])
    result = CampusGradesService(home=tmp_path, snapshot_path=snapshot).refresh()
    assert result["row_count"] == 1


def test_invalid_schema_rejected(tmp_path):
    snapshot = tmp_path / "grades.json"
    write_snapshot(snapshot, [row("内科学", "88")], schema="campus-grades-snapshot/2")
    result = CampusGradesService(home=tmp_path, snapshot_path=snapshot).refresh()
    assert result["result"] == "snapshot_invalid"


def test_account_isolation(tmp_path):
    major = tmp_path / "major.json"
    minor = tmp_path / "minor.json"
    write_snapshot(major, [row("内科学", "88")], account="major")
    write_snapshot(minor, [row("中医基础", "75")], account="minor",
                   captured_at="2026-11-19T21:00:00+08:00")

    CampusGradesService(home=tmp_path, snapshot_path=major).refresh()
    CampusGradesService(home=tmp_path, snapshot_path=minor).refresh()

    assert [r["course"] for r in CampusGradesService(home=tmp_path, account="major").get_grades()["records"]] == ["内科学"]
    assert [r["course"] for r in CampusGradesService(home=tmp_path, account="minor").get_grades()["records"]] == ["中医基础"]
