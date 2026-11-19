"""Campus 考试读取服务：宿主快照 → 校验 → SQLite 快照。

抽屉 UI 与后续 Honey 工具共用本服务；service 层保证「迟到的旧快照
不覆盖新结果」与「失败保留旧数据」两条业务约束。
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from honeyos.campus.repository import CampusRepository
from honeyos.campus.snapshot import (
    CampusSnapshotError,
    DEFAULT_ACCOUNT,
    ExamRow,
    GradeRow,
    MissingSnapshotError,
    TimetableRow,
    read_grades_snapshot,
    read_snapshot,
    read_timetable_snapshot,
)

STALE_AFTER_HOURS = 24


class CampusExamsService:
    def __init__(self, home: Path | str | None = None, snapshot_path: Path | str | None = None,
                 account: str | None = None):
        self.repository = CampusRepository(home=home)
        self.snapshot_path = Path(snapshot_path) if snapshot_path is not None else None
        self.account = account

    def get_exams(self) -> dict:
        data = self.repository.list_exams(self.account)
        metas = data["meta"]
        last_success_at = max((m["last_success_at"] for m in metas), default=None)
        captured_at = max((m["captured_at"] for m in metas), default=None)
        source = metas[0]["source"] if metas else None
        stale = _older_than_hours(captured_at, STALE_AFTER_HOURS) if captured_at else False
        return {
            "account": data["account"],
            "records": data["records"],
            "source": source,
            "captured_at": captured_at,
            "last_success_at": last_success_at,
            "row_count": len(data["records"]),
            "has_data": bool(metas),
            "stale": stale,
            "needs_capture": not metas,
        }

    def refresh(self) -> dict:
        """读取宿主快照并整批替换；宿主不存在新快照时返回可行动提示。"""
        try:
            snapshot = read_snapshot(
                self.snapshot_path,
                account=self.account or DEFAULT_ACCOUNT,
            )
        except MissingSnapshotError:
            return {
                "result": "snapshot_missing",
                "action": "open-host",
                "message": "尚未发现宿主快照：请在宿主中完成官方登录并进入考试查询页捕获，然后重试。",
            }
        except CampusSnapshotError as exc:
            return {"result": "snapshot_invalid", "action": "open-host", "message": str(exc)}

        source: str = snapshot["source"]
        captured_at: str = snapshot["captured_at"]
        account: str = snapshot["account"]
        rows: list[ExamRow] = snapshot["rows"]

        stored = self.repository.latest_captured_at(source, account=account, kind="exams")
        stored_at = _parse_iso(stored)
        new_at = _parse_iso(captured_at)
        if stored_at is not None and new_at is not None and stored_at >= new_at:
            return {
                "result": "no_new_snapshot",
                "account": account,
                "captured_at": stored,
                "message": "宿主快照未更新；请在宿主中重新捕获后再刷新。",
            }
        if new_at is None:
            return {"result": "snapshot_invalid", "action": "open-host",
                    "message": "快照捕获时间无法解析，已拒绝导入。"}

        batch_key = captured_at[:10]
        imported = self.repository.import_snapshot(
            source, batch_key, captured_at, rows, account=account,
        )
        payload = self.get_exams()
        payload.update({"result": "updated", "imported": imported})
        return payload


class CampusTimetableService:
    """课表读取服务：与考试同一套快照、过期、迟到与账号隔离规则。"""

    def __init__(self, home: Path | str | None = None, snapshot_path: Path | str | None = None,
                 account: str | None = None):
        self.repository = CampusRepository(home=home)
        self.snapshot_path = Path(snapshot_path) if snapshot_path is not None else None
        self.account = account

    def get_timetable(self) -> dict:
        data = self.repository.list_timetable(self.account)
        metas = data["meta"]
        last_success_at = max((m["last_success_at"] for m in metas), default=None)
        captured_at = max((m["captured_at"] for m in metas), default=None)
        source = metas[0]["source"] if metas else None
        stale = _older_than_hours(captured_at, STALE_AFTER_HOURS) if captured_at else False
        return {
            "account": data["account"],
            "records": data["records"],
            "source": source,
            "captured_at": captured_at,
            "last_success_at": last_success_at,
            "row_count": len(data["records"]),
            "has_data": bool(metas),
            "stale": stale,
            "needs_capture": not metas,
        }

    def refresh(self) -> dict:
        try:
            snapshot = read_timetable_snapshot(
                self.snapshot_path,
                account=self.account or DEFAULT_ACCOUNT,
            )
        except MissingSnapshotError:
            return {
                "result": "snapshot_missing",
                "action": "open-host",
                "message": "尚未发现课表快照：请在宿主中完成官方登录并打开「我的课表」，然后重试。",
            }
        except CampusSnapshotError as exc:
            return {"result": "snapshot_invalid", "action": "open-host", "message": str(exc)}

        source: str = snapshot["source"]
        captured_at: str = snapshot["captured_at"]
        account: str = snapshot["account"]
        rows: list[TimetableRow] = snapshot["rows"]

        stored = self.repository.latest_captured_at(source, account=account, kind="timetable")
        stored_at = _parse_iso(stored)
        new_at = _parse_iso(captured_at)
        if stored_at is not None and new_at is not None and stored_at >= new_at:
            return {
                "result": "no_new_snapshot",
                "account": account,
                "captured_at": stored,
                "message": "宿主课表快照未更新；请在宿主中重新捕获后再刷新。",
            }
        if new_at is None:
            return {"result": "snapshot_invalid", "action": "open-host",
                    "message": "课表快照捕获时间无法解析，已拒绝导入。"}

        batch_key = captured_at[:10]
        imported = self.repository.import_timetable(
            source, batch_key, captured_at, rows, account=account,
        )
        payload = self.get_timetable()
        payload.update({"result": "updated", "imported": imported})
        return payload


class CampusGradesService:
    """成绩读取服务：与考试、课表共用快照、过期、迟到与账号隔离规则。"""

    def __init__(self, home: Path | str | None = None, snapshot_path: Path | str | None = None,
                 account: str | None = None):
        self.repository = CampusRepository(home=home)
        self.snapshot_path = Path(snapshot_path) if snapshot_path is not None else None
        self.account = account

    def get_grades(self) -> dict:
        data = self.repository.list_grades(self.account)
        metas = data["meta"]
        last_success_at = max((m["last_success_at"] for m in metas), default=None)
        captured_at = max((m["captured_at"] for m in metas), default=None)
        source = metas[0]["source"] if metas else None
        stale = _older_than_hours(captured_at, STALE_AFTER_HOURS) if captured_at else False
        return {
            "account": data["account"],
            "records": data["records"],
            "source": source,
            "captured_at": captured_at,
            "last_success_at": last_success_at,
            "row_count": len(data["records"]),
            "has_data": bool(metas),
            "stale": stale,
            "needs_capture": not metas,
        }

    def refresh(self) -> dict:
        try:
            snapshot = read_grades_snapshot(
                self.snapshot_path,
                account=self.account or DEFAULT_ACCOUNT,
            )
        except MissingSnapshotError:
            return {
                "result": "snapshot_missing",
                "action": "open-host",
                "message": "尚未发现成绩快照：请在宿主中完成官方登录并打开成绩查询页，然后重试。",
            }
        except CampusSnapshotError as exc:
            return {"result": "snapshot_invalid", "action": "open-host", "message": str(exc)}

        source: str = snapshot["source"]
        captured_at: str = snapshot["captured_at"]
        account: str = snapshot["account"]
        rows: list[GradeRow] = snapshot["rows"]

        stored = self.repository.latest_captured_at(source, account=account, kind="grades")
        stored_at = _parse_iso(stored)
        new_at = _parse_iso(captured_at)
        if stored_at is not None and new_at is not None and stored_at >= new_at:
            return {
                "result": "no_new_snapshot",
                "account": account,
                "captured_at": stored,
                "message": "宿主成绩快照未更新；请在宿主中重新捕获后再刷新。",
            }
        if new_at is None:
            return {"result": "snapshot_invalid", "action": "open-host",
                    "message": "成绩快照捕获时间无法解析，已拒绝导入。"}

        batch_key = captured_at[:10]
        imported = self.repository.import_grades(
            source, batch_key, captured_at, rows, account=account,
        )
        payload = self.get_grades()
        payload.update({"result": "updated", "imported": imported})
        return payload


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _older_than_hours(iso_like: str, hours: int) -> bool:
    parsed = _parse_iso(iso_like)
    if parsed is None:
        return False
    age = datetime.now(timezone.utc) - parsed
    return age.total_seconds() > hours * 3600
