"""Trusted, single-owner attribution of existing canonical review events."""

from datetime import datetime, timezone
import json
from zoneinfo import ZoneInfo


def mark_day_dirty(db, plan_id, local_date):
    if db.execute("SELECT name FROM sqlite_master WHERE name='study_projection_dirty'").fetchone():
        db.execute("INSERT INTO study_projection_dirty VALUES (?,?,1) "
                   "ON CONFLICT(plan_id,local_date) DO UPDATE SET revision=revision+1",(plan_id,local_date))


def mark_event_dirty(db, plan_id, timestamp):
    if not plan_id:
        return
    from honeyos.core.time import local_timezone
    zone=local_timezone()
    if db.execute("SELECT name FROM sqlite_master WHERE name='study_growth_settings'").fetchone():
        row=db.execute("SELECT settings_json FROM study_growth_settings WHERE plan_id=?",(plan_id,)).fetchone()
        if row:
            zone=ZoneInfo(json.loads(row["settings_json"])["timezone"])
    instant=datetime.fromisoformat(timestamp)
    if instant.tzinfo is None:
        instant=instant.replace(tzinfo=timezone.utc)
    mark_day_dirty(db,plan_id,instant.astimezone(zone).date().isoformat())


TABLES = {"attempt": "study_learning_attempts", "recall": "study_learning_recalls"}


def link_event(db, kind, event_id, plan_id):
    if plan_id is not None:
        if not isinstance(plan_id, str) or db.execute(
            "SELECT id FROM study_plans WHERE id=? AND status NOT IN ('completed','archived')", (plan_id,),
        ).fetchone() is None:
            raise ValueError("学习事件所属计划不存在。")
    row = db.execute(
        "SELECT plan_id FROM study_activity_attribution WHERE kind=? AND event_id=?",
        (kind, event_id),
    ).fetchone()
    if row is not None and row["plan_id"] != plan_id:
        raise ValueError("此学习事件已有归属，请通过事件归属入口调整。")
    event=db.execute(f"SELECT created_at FROM {TABLES[kind]} WHERE id=?",(event_id,)).fetchone()
    if event:
        mark_event_dirty(db,plan_id,event["created_at"])
    db.execute(
        "INSERT OR IGNORE INTO study_activity_attribution(kind,event_id,plan_id) VALUES (?,?,?)",
        (kind, event_id, plan_id),
    )


def assign_event(study, kind, event_id, plan_id):
    if kind not in TABLES:
        raise ValueError("不支持的事件类型。")
    with study.repository._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute(f"SELECT id FROM {TABLES[kind]} WHERE id=?", (event_id,)).fetchone() is None:
            raise KeyError(event_id)
        if plan_id is not None and db.execute(
            "SELECT id FROM study_plans WHERE id=? AND status NOT IN ('completed','archived')", (plan_id,),
        ).fetchone() is None:
            raise ValueError("计划不存在。")
        event=db.execute(f"SELECT created_at FROM {TABLES[kind]} WHERE id=?",(event_id,)).fetchone()
        previous=db.execute("SELECT plan_id FROM study_activity_attribution WHERE kind=? AND event_id=?",(kind,event_id)).fetchone()
        if previous:
            mark_event_dirty(db,previous["plan_id"],event["created_at"])
        mark_event_dirty(db,plan_id,event["created_at"])
        db.execute(
            "INSERT INTO study_activity_attribution VALUES (?,?,?) "
            "ON CONFLICT(kind,event_id) DO UPDATE SET plan_id=excluded.plan_id",
            (kind, event_id, plan_id),
        )
