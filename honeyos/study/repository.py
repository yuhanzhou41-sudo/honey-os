from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import StudyPlan
from .validation import validate_study_plan


class StudyPlanNotFoundError(KeyError):
    pass


class StudyRepository:
    """SQLite persistence for canonical StudyPlan v1 objects."""

    def __init__(self, home: Path | str | None = None):
        root = Path(home) if home is not None else Path.home() / ".honeyos"
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

    def save_plan(self, plan: StudyPlan) -> StudyPlan:
        plan = validate_study_plan(plan)

        with self._connect() as conn:
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

            # Tasks are a child collection of the canonical plan. Replacing
            # them prevents deleted tasks from surviving an update.
            conn.execute(
                "DELETE FROM study_tasks WHERE plan_id = ?",
                (plan.id,),
            )

            for task in plan.tasks:
                conn.execute(
                    """
                    INSERT INTO study_tasks (
                        id, plan_id, title, description,
                        scheduled_date, planned_minutes,
                        status, order_index, review_required,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

        return self.get_plan(plan.id)

    def get_plan(self, plan_id: str) -> StudyPlan:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM study_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()

            if row is None:
                raise StudyPlanNotFoundError(plan_id)

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
            "tasks": [
                {
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
