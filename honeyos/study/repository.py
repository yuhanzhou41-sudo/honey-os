from __future__ import annotations

from contextlib import contextmanager, nullcontext
import json
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta

from honeyos.core.constants import get_honeyos_home

from .models import StudyPlan, StudyResource
from .validation import validate_study_plan


def version_matches(actual, expected):
    try:
        first, second = datetime.fromisoformat(actual), datetime.fromisoformat(expected)
        return first.tzinfo is not None and second.tzinfo is not None and first == second
    except (ValueError, TypeError):
        return False


class StudyPlanNotFoundError(KeyError):
    pass


class StudyResourceNotFoundError(KeyError):
    pass


class StudyRepository:
    """SQLite persistence for canonical StudyPlan objects."""

    def __init__(self, home: Path | str | None = None):
        root = Path(home) if home is not None else get_honeyos_home()
        self.study_dir = root / "study"
        self.db_path = self.study_dir / "study.db"
        self.study_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS study_plans (
                    id TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    status TEXT NOT NULL,
                    focus_minutes INTEGER NOT NULL,
                    break_minutes INTEGER NOT NULL,
                    long_break_minutes INTEGER NOT NULL,
                    long_break_after_sessions INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    goals_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS study_task_completion_events (
                    task_id TEXT PRIMARY KEY REFERENCES study_tasks(id) ON DELETE CASCADE,
                    completed_at TEXT NOT NULL,active INTEGER NOT NULL,revision INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS study_projection_dirty (
                    plan_id TEXT NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
                    local_date TEXT NOT NULL,revision INTEGER NOT NULL,
                    PRIMARY KEY(plan_id,local_date)
                );
                CREATE TABLE IF NOT EXISTS study_activity_archive (
                    kind TEXT NOT NULL,event_id TEXT NOT NULL,payload_json TEXT NOT NULL,
                    PRIMARY KEY(kind,event_id)
                );

                CREATE TABLE IF NOT EXISTS study_activity_attribution (
                    kind TEXT NOT NULL, event_id TEXT NOT NULL,
                    plan_id TEXT REFERENCES study_plans(id) ON DELETE SET NULL,
                    PRIMARY KEY(kind,event_id)
                );

                CREATE INDEX IF NOT EXISTS study_activity_plan ON study_activity_attribution(plan_id,kind,event_id);

                CREATE TABLE IF NOT EXISTS study_daily_capacity (
                    local_date TEXT PRIMARY KEY,
                    minutes INTEGER NOT NULL CHECK(minutes BETWEEN 0 AND 1440)
                );

                CREATE TABLE IF NOT EXISTS study_plan_definitions (
                    plan_id TEXT PRIMARY KEY
                        REFERENCES study_plans(id) ON DELETE CASCADE,
                    definition_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS study_tasks (
                    id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL
                        REFERENCES study_plans(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    scheduled_date TEXT NOT NULL,
                    planned_minutes INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    order_index INTEGER NOT NULL,
                    review_required INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_study_tasks_plan
                    ON study_tasks(plan_id);

                CREATE INDEX IF NOT EXISTS idx_study_tasks_date
                    ON study_tasks(scheduled_date);

                CREATE TABLE IF NOT EXISTS study_sessions (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL
                        REFERENCES study_tasks(id) ON DELETE CASCADE,
                    session_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT,
                    expected_end_at TEXT,
                    ended_at TEXT,
                    planned_minutes INTEGER NOT NULL,
                    actual_minutes INTEGER NOT NULL DEFAULT 0,
                    user_summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS study_resources (
                    id TEXT PRIMARY KEY,
                    attachment_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    course_or_subject TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def capacity_report(self, plan: StudyPlan) -> list[dict]:
        with self._connect() as conn:
            conn.execute("BEGIN")
            return self._capacity_report(conn, plan)

    def _capacity_report(self, conn, plan: StudyPlan) -> list[dict]:
        candidate: dict[str, int] = {}
        for item in [*plan.tasks, *plan.flex_slots]:
            day = item.scheduled_date.isoformat()
            candidate[day] = candidate.get(day, 0) + item.planned_minutes
        other = dict(conn.execute(
            "SELECT t.scheduled_date, SUM(t.planned_minutes) FROM study_tasks t "
            "JOIN study_plans p ON p.id=t.plan_id "
            "WHERE p.status='active' AND p.id!=? GROUP BY t.scheduled_date",
            (plan.id,),
        ).fetchall())
        definitions = conn.execute(
            "SELECT d.definition_json FROM study_plan_definitions d "
            "JOIN study_plans p ON p.id=d.plan_id WHERE p.status='active' AND p.id!=?",
            (plan.id,),
        ).fetchall()
        for row in definitions:
            for slot in json.loads(row["definition_json"]).get("flex_slots", []):
                day = slot["scheduled_date"]
                other[day] = other.get(day, 0) + slot["planned_minutes"]
        limits = dict(conn.execute("SELECT local_date, minutes FROM study_daily_capacity").fetchall())
        days = sorted(day for day in candidate.keys() | other.keys() | limits.keys()
                      if plan.start_date.isoformat() <= day <= plan.end_date.isoformat())
        return [{
            "date": day, "candidate_minutes": candidate.get(day, 0),
            "other_minutes": other.get(day, 0),
            "total_minutes": candidate.get(day, 0) + other.get(day, 0),
            "limit_minutes": limits.get(day),
            "verified": day in limits,
            "overloaded": day in limits and candidate.get(day, 0) + other.get(day, 0) > limits[day],
        } for day in days]

    def set_daily_capacity(self, local_date: str, minutes: int | None) -> None:
        if date.fromisoformat(local_date).isoformat() != local_date:
            raise ValueError("日期须为 YYYY-MM-DD。")
        if minutes is not None and (type(minutes) is not int or not 0 <= minutes <= 1440):
            raise ValueError("每日学习上限须为0至1440的整数分钟。")
        with self._connect() as conn:
            if minutes is None:
                conn.execute("DELETE FROM study_daily_capacity WHERE local_date=?", (local_date,))
            else:
                conn.execute(
                    "INSERT INTO study_daily_capacity (local_date, minutes) VALUES (?,?) "
                    "ON CONFLICT(local_date) DO UPDATE SET minutes=excluded.minutes",
                    (local_date, minutes),
                )

    def _check_capacity_increase(self, conn, plan: StudyPlan) -> None:
        if plan.status.value not in {"active", "draft"}:
            return
        previous = conn.execute("SELECT status FROM study_plans WHERE id=?", (plan.id,)).fetchone()
        previous_minutes = {}
        if previous and previous["status"] == plan.status.value:
            previous_minutes = dict(conn.execute(
                "SELECT scheduled_date, SUM(planned_minutes) FROM study_tasks "
                "WHERE plan_id=? GROUP BY scheduled_date", (plan.id,),
            ).fetchall())
            definition = conn.execute(
                "SELECT definition_json FROM study_plan_definitions WHERE plan_id=?", (plan.id,),
            ).fetchone()
            if definition:
                for slot in json.loads(definition["definition_json"]).get("flex_slots", []):
                    day = slot["scheduled_date"]
                    previous_minutes[day] = previous_minutes.get(day, 0) + slot["planned_minutes"]
        for day in self._capacity_report(conn, plan):
            if day["overloaded"] and day["candidate_minutes"] > previous_minutes.get(day["date"], 0):
                raise ValueError(
                    f'{day["date"]} 学习安排 {day["total_minutes"]} 分钟，'
                    f'超过已设置上限 {day["limit_minutes"]} 分钟。'
                )

    def save_plan(self, plan: StudyPlan, *, expected_updated_at=None, new=False, connection=None) -> StudyPlan:
        plan = validate_study_plan(plan)

        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            if connection is None:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT updated_at FROM study_plans WHERE id=?", (plan.id,)).fetchone()
            closure_table=conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='study_plan_closures'").fetchone()
            if closure_table and conn.execute("SELECT plan_id FROM study_plan_closures WHERE plan_id=?",(plan.id,)).fetchone():
                raise ValueError("计划已结束归档，不能修改历史计划。")
            if new and row:
                return self.get_plan(plan.id)
            if expected_updated_at is not None and (row is None or not version_matches(row["updated_at"], expected_updated_at)):
                raise ValueError("计划已变化，请重新预览再确认。")
            if row:
                previous_time=datetime.fromisoformat(row["updated_at"])
                if plan.updated_at<=previous_time:
                    plan.updated_at=previous_time+timedelta(microseconds=1)
            self._check_capacity_increase(conn, plan)
            conn.execute(
                """
                INSERT INTO study_plans (
                    id, schema_version, title, description,
                    start_date, end_date, status,
                    focus_minutes, break_minutes,
                    long_break_minutes, long_break_after_sessions,
                    source_type, goals_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    schema_version=excluded.schema_version,
                    title=excluded.title,
                    description=excluded.description,
                    start_date=excluded.start_date,
                    end_date=excluded.end_date,
                    status=excluded.status,
                    focus_minutes=excluded.focus_minutes,
                    break_minutes=excluded.break_minutes,
                    long_break_minutes=excluded.long_break_minutes,
                    long_break_after_sessions=excluded.long_break_after_sessions,
                    source_type=excluded.source_type,
                    goals_json=excluded.goals_json,
                    updated_at=excluded.updated_at
                """,
                (
                    plan.id,
                    plan.schema_version,
                    plan.title,
                    plan.description,
                    plan.start_date.isoformat(),
                    plan.end_date.isoformat(),
                    plan.status.value,
                    plan.focus_minutes,
                    plan.break_minutes,
                    plan.long_break_minutes,
                    plan.long_break_after_sessions,
                    plan.source_type.value,
                    json.dumps(plan.goals, ensure_ascii=False),
                    plan.created_at.isoformat(),
                    plan.updated_at.isoformat(),
                ),
            )

            from .activity import mark_day_dirty
            changed_days={task.scheduled_date.isoformat() for task in plan.tasks}
            changed_days.update(slot.scheduled_date.isoformat() for slot in plan.flex_slots)
            changed_days.update(item[0] for item in conn.execute("SELECT scheduled_date FROM study_tasks WHERE plan_id=?",(plan.id,)))
            old_definition=conn.execute("SELECT definition_json FROM study_plan_definitions WHERE plan_id=?",(plan.id,)).fetchone()
            if old_definition:
                changed_days.update(item["scheduled_date"] for item in json.loads(old_definition[0]).get("flex_slots",[]))
            for day in changed_days:
                mark_day_dirty(conn,plan.id,day)
            definition = {
                "flex_slots": [slot.model_dump(mode="json") for slot in plan.flex_slots],
                "tasks": {
                    task.id: {
                        "priority": task.priority,
                        "minimum_required": task.minimum_required,
                        "kind": task.kind,
                    }
                    for task in plan.tasks
                },
            }
            conn.execute(
                "INSERT INTO study_plan_definitions (plan_id, definition_json) VALUES (?, ?) "
                "ON CONFLICT(plan_id) DO UPDATE SET definition_json=excluded.definition_json",
                (plan.id, json.dumps(definition, ensure_ascii=False)),
            )

            retained = {task.id for task in plan.tasks}
            old_ids = conn.execute("SELECT id FROM study_tasks WHERE plan_id=?", (plan.id,)).fetchall()
            conn.executemany("DELETE FROM study_tasks WHERE plan_id=? AND id=?",
                             ((plan.id, row["id"]) for row in old_ids if row["id"] not in retained))

            for task in plan.tasks:
                owner = conn.execute("SELECT plan_id,status FROM study_tasks WHERE id=?", (task.id,)).fetchone()
                if owner is not None and owner["plan_id"] != plan.id:
                    raise ValueError("任务编号已属于另一个计划。")
                conn.execute(
                    """
                    INSERT INTO study_tasks (
                        id, plan_id, title, description,
                        scheduled_date, planned_minutes,
                        status, order_index, review_required,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title, description=excluded.description,
                        scheduled_date=excluded.scheduled_date, planned_minutes=excluded.planned_minutes,
                        status=excluded.status, order_index=excluded.order_index,
                        review_required=excluded.review_required, updated_at=excluded.updated_at
                    WHERE study_tasks.plan_id=excluded.plan_id
                    """,
                    (
                        task.id,
                        plan.id,
                        task.title,
                        task.description,
                        task.scheduled_date.isoformat(),
                        task.planned_minutes,
                        task.status.value,
                        task.order_index,
                        int(task.review_required),
                        task.created_at.isoformat(),
                        task.updated_at.isoformat(),
                    ),
                )
                if owner and owner["status"] != task.status.value:
                    if task.status.value == "completed":
                        conn.execute(
                            "INSERT INTO study_task_completion_events VALUES (?,?,1,1) "
                            "ON CONFLICT(task_id) DO UPDATE SET completed_at=excluded.completed_at,active=1,revision=revision+1",
                            (task.id,plan.updated_at.isoformat()),
                        )
                    elif owner["status"] == "completed":
                        conn.execute("UPDATE study_task_completion_events SET active=0 WHERE task_id=?",(task.id,))


        return plan if connection is not None else self.get_plan(plan.id)

    def save_new_plan(self, plan: StudyPlan) -> StudyPlan:
        return self.save_plan(plan, new=True)

    def get_plan(self, plan_id: str) -> StudyPlan:
        with self._connect() as conn:
            conn.execute("BEGIN")
            row = conn.execute(
                "SELECT * FROM study_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()

            if row is None:
                raise StudyPlanNotFoundError(plan_id)

            definition_row = conn.execute(
                "SELECT definition_json FROM study_plan_definitions WHERE plan_id=?",
                (plan_id,),
            ).fetchone()
            definition = json.loads(definition_row["definition_json"]) if definition_row else {}

            task_rows = conn.execute(
                """
                SELECT *
                FROM study_tasks
                WHERE plan_id = ?
                ORDER BY scheduled_date, order_index, id
                """,
                (plan_id,),
            ).fetchall()

        raw = {
            "id": row["id"],
            "schema_version": row["schema_version"],
            "title": row["title"],
            "description": row["description"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "status": row["status"],
            "focus_minutes": row["focus_minutes"],
            "break_minutes": row["break_minutes"],
            "long_break_minutes": row["long_break_minutes"],
            "long_break_after_sessions": row[
                "long_break_after_sessions"
            ],
            "source_type": row["source_type"],
            "goals": json.loads(row["goals_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "flex_slots": definition.get("flex_slots", []),
            "tasks": [
                {
                    **definition.get("tasks", {}).get(task["id"], {}),
                    "id": task["id"],
                    "plan_id": task["plan_id"],
                    "title": task["title"],
                    "description": task["description"],
                    "scheduled_date": task["scheduled_date"],
                    "planned_minutes": task["planned_minutes"],
                    "status": task["status"],
                    "order_index": task["order_index"],
                    "review_required": bool(task["review_required"]),
                    "created_at": task["created_at"],
                    "updated_at": task["updated_at"],
                }
                for task in task_rows
            ],
        }

        return validate_study_plan(raw)

    def list_plans(self) -> list[StudyPlan]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id
                FROM study_plans
                ORDER BY start_date, created_at, id
                """
            ).fetchall()

        return [self.get_plan(row["id"]) for row in rows]

    def delete_plan(self, plan_id: str) -> None:
        with self._connect() as conn:
            result = conn.execute(
                "DELETE FROM study_plans WHERE id = ?",
                (plan_id,),
            )

            if result.rowcount == 0:
                raise StudyPlanNotFoundError(plan_id)

    # === Phase 4 Study Library resource persistence ===
    @contextmanager
    def resource_transaction(self):
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            yield conn

    def save_resource(self, resource: StudyResource, *, connection=None) -> StudyResource:
        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            conn.execute("""
                INSERT INTO study_resources(id, attachment_id, title, resource_type, course_or_subject, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    attachment_id=excluded.attachment_id,
                    title=excluded.title,
                    resource_type=excluded.resource_type,
                    course_or_subject=excluded.course_or_subject,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
            """, (resource.id, resource.attachment_id, resource.title, resource.resource_type,
                  resource.course_or_subject, json.dumps(resource.metadata, ensure_ascii=False),
                  resource.created_at.isoformat(), resource.updated_at.isoformat()))
        return resource

    def find_resource_by_local_digest(self, digest: str, *, connection=None) -> StudyResource | None:
        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM study_resources "
                "WHERE json_extract(metadata_json, '$.local_source.sha256') = ? "
                "ORDER BY created_at, id LIMIT 1",
                (digest,),
            ).fetchone()
        return self._resource_from_row(row) if row is not None else None

    def find_resource_by_textbook_section(
        self, book_id: str, section_id: str, *, connection=None
    ) -> StudyResource | None:
        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM study_resources "
                "WHERE resource_type = 'textbook' "
                "AND json_extract(metadata_json, '$.textbook.book_id') = ? "
                "AND json_extract(metadata_json, '$.textbook.section_id') = ? "
                "ORDER BY created_at, id LIMIT 1",
                (book_id, section_id),
            ).fetchone()
        return self._resource_from_row(row) if row is not None else None

    def find_indexed_resource_by_attachments(self, attachment_ids: list[str], *, connection=None) -> StudyResource | None:
        if not attachment_ids:
            return None
        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            row = conn.execute(
                "SELECT r.* FROM study_resources r JOIN study_resource_content c ON c.resource_id = r.id "
                "WHERE r.attachment_id IN (SELECT value FROM json_each(?)) "
                "ORDER BY r.created_at, r.id LIMIT 1",
                (json.dumps(attachment_ids),),
            ).fetchone()
        return self._resource_from_row(row) if row is not None else None

    def local_source_paths(self, *, connection) -> set[Path]:
        rows = connection.execute(
            "SELECT json_extract(metadata_json, '$.local_source.path') AS path "
            "FROM study_resources WHERE json_type(metadata_json, '$.local_source.path') = 'text'"
        )
        return {Path(row["path"]) for row in rows}

    def get_resource(self, resource_id: str, *, connection=None) -> StudyResource:
        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            row = conn.execute("SELECT * FROM study_resources WHERE id = ?", (resource_id,)).fetchone()
        if row is None:
            raise StudyResourceNotFoundError(resource_id)
        return self._resource_from_row(row)

    @staticmethod
    def _resource_from_row(row: sqlite3.Row) -> StudyResource:
        return StudyResource.model_validate({
            "id":row["id"], "attachment_id":row["attachment_id"], "title":row["title"],
            "resource_type":row["resource_type"], "course_or_subject":row["course_or_subject"],
            "metadata":json.loads(row["metadata_json"] or "{}"),
            "created_at":row["created_at"], "updated_at":row["updated_at"],
        })

    def list_resources(self, *, course_or_subject: str = "", resource_type: str = "") -> list[StudyResource]:
        where=[]; params=[]
        if course_or_subject:
            where.append("course_or_subject = ?"); params.append(course_or_subject)
        if resource_type:
            where.append("resource_type = ?"); params.append(resource_type)
        sql="SELECT id FROM study_resources"
        if where: sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC, id ASC"
        with self._connect() as conn:
            rows=conn.execute(sql, tuple(params)).fetchall()
        return [self.get_resource(row["id"]) for row in rows]

    def delete_resource(self, resource_id: str, *, connection=None) -> None:
        with (nullcontext(connection) if connection is not None else self._connect()) as conn:
            result=conn.execute("DELETE FROM study_resources WHERE id = ?", (resource_id,))
        if result.rowcount == 0:
            raise StudyResourceNotFoundError(resource_id)

