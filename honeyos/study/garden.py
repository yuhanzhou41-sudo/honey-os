"""Plan plants and inspectable calendar summaries over real Study facts.

Finished plants keep a small immutable daily projection after plan deletion.
This is an archive of facts, not a second task or reward store.
"""
from datetime import date, datetime, timedelta
import json
from zoneinfo import ZoneInfo

FIELDS = ("tasks", "completed", "focus_minutes", "attempts", "correct", "recalls",
          "mastered", "wrong_answers", "flex_minutes", "reward_points")


class StudyGarden:
    def __init__(self, study, *, memory=None):
        from .learning import StudyLearningMemory
        self.study = study
        self.memory = memory or StudyLearningMemory(study)
        with study.repository._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS study_garden_plants (
                plan_id TEXT PRIMARY KEY, record_json TEXT NOT NULL, updated_at TEXT NOT NULL
            )""")

    def prepare(self, plan_id, *, closure=None):
        plan = self.study.get_plan(plan_id)
        state = self.memory.growth.state(plan_id)
        setting = state.get("settings") or {}
        zone_name = setting.get("timezone", "Asia/Shanghai")
        zone = ZoneInfo(zone_name)
        today = self.study._now().astimezone(zone).date()
        cutoff = today
        if closure and closure.get("closed_at"):
            cutoff = datetime.fromisoformat(closure["closed_at"]).astimezone(zone).date()
        days = {task.scheduled_date for task in plan.tasks if task.scheduled_date <= cutoff}
        days.update(slot.scheduled_date for slot in plan.flex_slots if slot.scheduled_date <= cutoff)
        with self.study.repository._connect() as db:
            for kind, table in (("attempt", "study_learning_attempts"), ("recall", "study_learning_recalls")):
                for row in db.execute(f"SELECT e.created_at FROM {table} e JOIN study_activity_attribution a "
                                      "ON a.event_id=e.id AND a.kind=? WHERE a.plan_id=?", (kind, plan_id)):
                    days.add(datetime.fromisoformat(row[0]).astimezone(zone).date())
            for row in db.execute("SELECT s.started_at,s.ended_at FROM study_sessions s JOIN study_tasks t "
                                  "ON t.id=s.task_id WHERE t.plan_id=? AND s.status='completed' AND s.session_type='focus'",
                                  (plan_id,)):
                if not row[0] or not row[1]:
                    continue
                day = datetime.fromisoformat(row[0]).astimezone(zone).date()
                end = min(datetime.fromisoformat(row[1]).astimezone(zone).date(), cutoff)
                while day <= end:
                    days.add(day)
                    day += timedelta(days=1)
        # Same authoritative projection used by reminders and learning chat context.
        daily = [self.memory.snapshot(plan_id, day.isoformat(), growth_state=state)
                 for day in sorted(days) if day <= cutoff]
        reason = closure.get("reason") if closure else None
        planted = reason == "completed" or (not closure and plan.status.value == "completed")
        return {"plan_id": plan_id, "title": plan.title, "plan_status": plan.status.value,
                "start_date": plan.start_date.isoformat(), "end_date": plan.end_date.isoformat(),
                "enabled": state["enabled"], "plant": state["plant"], "sunlight": state["sunlight"],
                "tasks": len(plan.tasks), "completed": sum(task.status.value == "completed" for task in plan.tasks),
                "standard_days": state.get("standard_days", 0), "planted": planted,
                "closed": bool(closure) or plan.status.value in {"completed", "archived"},
                "closed_at": closure.get("closed_at", self.study._now().isoformat()) if closure else None,
                "summary": closure.get("summary") if closure else None,
                "final_stats": json.loads(closure["stats_json"]) if closure else None,
                "timezone": zone_name, "as_of": cutoff.isoformat(), "daily": daily,
                "updated_at": self.study._now().isoformat()}

    def save(self, record, connection=None):
        def write(db):
            db.execute("INSERT INTO study_garden_plants VALUES (?,?,?) ON CONFLICT(plan_id) "
                       "DO UPDATE SET record_json=excluded.record_json,updated_at=excluded.updated_at "
                       "WHERE json_extract(study_garden_plants.record_json,'$.closed')=0",
                       (record["plan_id"], json.dumps(record, ensure_ascii=False), record["updated_at"]))
        if connection is not None:
            write(connection)
        else:
            with self.study.repository._connect() as db:
                write(db)

    def records(self):
        with self.study.repository._connect() as db:
            records = {row["plan_id"]: json.loads(row["record_json"])
                       for row in db.execute("SELECT * FROM study_garden_plants")}
        existing = {plan.id for plan in self.study.list_plans()}
        for plan_id in existing:
            old = records.get(plan_id)
            if old and old["closed"]:
                continue
            closure = self.memory.closure(plan_id)
            if not self.memory.growth.settings(plan_id) and not closure:
                continue
            record = self.prepare(plan_id, closure=closure)
            if not record["closed"]:
                record["plan_status"] = self.study.get_plan(plan_id).status.value
            self.save(record)
            records[plan_id] = record
        return [record for key, record in records.items() if key in existing or record["closed"]]

    def listing(self):
        cards = []
        for record in self.records():
            card = {key: value for key, value in record.items() if key != "daily"}
            cards.append(card)
        return {"plants": sorted(cards, key=lambda item: (item["closed"], item["title"], item["plan_id"]))}

    def summary(self, plan_id, period, anchor):
        if period not in {"week", "month", "year"}:
            raise ValueError("请选择周、月或年。")
        point = date.fromisoformat(anchor)
        if period == "week":
            start = point - timedelta(days=point.weekday())
            end = start + timedelta(days=6)
        elif period == "month":
            start = point.replace(day=1)
            next_month = date(point.year + (point.month == 12), point.month % 12 + 1, 1)
            end = next_month - timedelta(days=1)
        else:
            start, end = date(point.year, 1, 1), date(point.year, 12, 31)
        record = next((item for item in self.records() if item["plan_id"] == plan_id), None)
        if record is None:
            raise KeyError(plan_id)
        days = [day for day in record["daily"] if start.isoformat() <= day["date"] <= end.isoformat()]
        total = {key: round(sum(day.get(key, 0) for day in days), 2) for key in FIELDS}
        total["completion_rate"] = round(total["completed"] / total["tasks"], 4) if total["tasks"] else None
        total["standard_days"] = sum(day["level"] in {"standard", "full"} for day in days)
        label = {"week": "本周", "month": "本月", "year": "本年"}[period]
        body = (f"{label}完成{total['completed']}/{total['tasks']}项任务，专注{total['focus_minutes']}分钟；"
                f"练习{total['attempts']}次、答对{total['correct']}次，闪卡复述{total['recalls']}次，"
                f"获得{total['reward_points']}阳光。") if days else "这个时段暂无学习记录。"
        return {"plan_id": plan_id, "period": period, "start_date": start.isoformat(),
                "end_date": end.isoformat(), "as_of": record["as_of"], "archived": record["closed"],
                "body": body, "stats": total, "days": days, "final_summary": record["summary"],
                "final_stats": record["final_stats"]}
