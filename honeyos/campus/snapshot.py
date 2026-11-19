"""读取 CampusHost 写出的脱敏考试快照。

宿主在受控 WebView2 会话内仅提取考试表的四个业务字段，按
``campus-exams-snapshot/1`` 契约写出到本机受保护目录。本模块只做
读取、契约校验与容量限制，不做任何网络访问，也不保留页面原文。
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_SCHEMA = "campus-exams-snapshot/1"
SNAPSHOT_FILE = "exams.latest.json"
MAX_ROWS = 500
MAX_CELL = 200

TIMETABLE_SCHEMA = "campus-timetable-snapshot/1"
TIMETABLE_FILE = "timetable.latest.json"
MAX_TIMETABLE_ROWS = 500


class CampusSnapshotError(Exception):
    """快照不可用（缺失、损坏或契约不符）。"""


class MissingSnapshotError(CampusSnapshotError):
    pass


class InvalidSnapshotError(CampusSnapshotError):
    pass


@dataclass(frozen=True)
class ExamRow:
    course: str
    exam_date: str
    arrangement: str
    location: str

    @property
    def fingerprint(self) -> str:
        joined = "\x1f".join(
            (self.course, self.exam_date, self.arrangement, self.location)
        ).encode("utf-8")
        return hashlib.sha256(joined).hexdigest()


@dataclass(frozen=True)
class TimetableRow:
    day: str
    period: str
    detail: str

    @property
    def fingerprint(self) -> str:
        joined = "\x1f".join((self.day, self.period, self.detail)).encode("utf-8")
        return hashlib.sha256(joined).hexdigest()


def default_snapshot_path(file_name: str = SNAPSHOT_FILE) -> Path:
    """宿主快照默认位置：Windows 直取 %LOCALAPPDATA%；WSL 侧经 /mnt/c 读取。

    可用 ``HONEYOS_CAMPUS_SNAPSHOT`` 覆盖；WSL 下 Windows 用户名可用
    ``HONEYOS_WINDOWS_USER`` 指定，默认取当前用户名。
    """
    override = os.environ.get("HONEYOS_CAMPUS_SNAPSHOT")
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "HoneyOS" / "campus" / "snapshots" / file_name
    windows_user = (
        os.environ.get("HONEYOS_WINDOWS_USER")
        or os.environ.get("USER")
        or ""
    )
    if not windows_user:
        raise InvalidSnapshotError(
            "无法定位宿主快照：请设置 HONEYOS_CAMPUS_SNAPSHOT 或 HONEYOS_WINDOWS_USER。"
        )
    return (
        Path("/mnt/c/Users") / windows_user
        / "AppData" / "Local" / "HoneyOS" / "campus" / "snapshots" / file_name
    )


def _cell(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:MAX_CELL]


def _parse_captured_at(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise InvalidSnapshotError("快照缺少捕获时间。")
    try:
        parsed = datetime.fromisoformat(value[:64])
    except ValueError as exc:
        raise InvalidSnapshotError("快照捕获时间无法解析。") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def normalize_snapshot(payload: object) -> dict:
    if not isinstance(payload, dict) or payload.get("schema") != SNAPSHOT_SCHEMA:
        raise InvalidSnapshotError("快照 schema 不符。")
    source = payload.get("source")
    if not isinstance(source, str) or not source:
        raise InvalidSnapshotError("快照缺少来源。")
    captured_at = _parse_captured_at(payload.get("captured_at"))
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        raise InvalidSnapshotError("快照缺少考试行。")
    rows: list[ExamRow] = []
    seen: set[str] = set()
    for raw in raw_rows[:MAX_ROWS]:
        if not isinstance(raw, dict):
            continue
        row = ExamRow(
            course=_cell(raw.get("course")),
            exam_date=_cell(raw.get("exam_date")),
            arrangement=_cell(raw.get("arrangement")),
            location=_cell(raw.get("location")),
        )
        if not (row.course or row.exam_date or row.arrangement or row.location):
            continue
        if row.fingerprint in seen:
            continue
        seen.add(row.fingerprint)
        rows.append(row)
    return {
        "schema": SNAPSHOT_SCHEMA,
        "captured_at": captured_at,
        "source": source[:128],
        "rows": rows,
    }


def read_snapshot(path: Path | str | None = None) -> dict:
    snapshot_path = Path(path) if path is not None else default_snapshot_path()
    if not snapshot_path.is_file():
        raise MissingSnapshotError(str(snapshot_path))
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidSnapshotError(f"快照文件无法读取：{exc}") from exc
    return normalize_snapshot(payload)


def normalize_timetable(payload: object) -> dict:
    if not isinstance(payload, dict) or payload.get("schema") != TIMETABLE_SCHEMA:
        raise InvalidSnapshotError("课表快照 schema 不符。")
    source = payload.get("source")
    if not isinstance(source, str) or not source:
        raise InvalidSnapshotError("课表快照缺少来源。")
    captured_at = _parse_captured_at(payload.get("captured_at"))
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        raise InvalidSnapshotError("课表快照缺少课程行。")
    rows: list[TimetableRow] = []
    seen: set[str] = set()
    for raw in raw_rows[:MAX_TIMETABLE_ROWS]:
        if not isinstance(raw, dict):
            continue
        row = TimetableRow(
            day=_cell(raw.get("day")),
            period=_cell(raw.get("period")),
            detail=_cell(raw.get("detail")),
        )
        if not row.detail:
            continue
        if row.fingerprint in seen:
            continue
        seen.add(row.fingerprint)
        rows.append(row)
    return {
        "schema": TIMETABLE_SCHEMA,
        "captured_at": captured_at,
        "source": source[:128],
        "rows": rows,
    }


def read_timetable_snapshot(path: Path | str | None = None) -> dict:
    snapshot_path = (
        Path(path) if path is not None else default_snapshot_path(TIMETABLE_FILE)
    )
    if not snapshot_path.is_file():
        raise MissingSnapshotError(str(snapshot_path))
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidSnapshotError(f"课表快照文件无法读取：{exc}") from exc
    return normalize_timetable(payload)
