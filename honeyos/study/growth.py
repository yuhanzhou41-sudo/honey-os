"""Plan-scoped growth projections and reversible flex use over canonical facts."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import StudyFlexSlot, StudyTaskStatus
from .review import StudyReview


class GrowthSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = "Asia/Shanghai"
    minimum_mode: bool = Field(default=False, strict=True)
    practice_points: int = Field(default=1, ge=0, le=100)
    focus_block_points: int = Field(default=5, ge=0, le=100)
    daily_rewards: tuple[int, int, int] = (10, 20, 30)

    @model_validator(mode="after")
    def validate_rewards(self):
        if any(point<0 or point>1000 for point in self.daily_rewards):
            raise ValueError("每日奖励须为0至1000的非负分值。")
        return self


def day_level(tasks, minimum_mode=False):
    if not tasks:
        return "no_tasks"
    done = lambda task: task.status is StudyTaskStatus.COMPLETED
    if all(done(task) for task in tasks):
        return "full"
    standard = [task for task in tasks if task.priority != "optional"]
    if standard and all(done(task) for task in standard):
        return "standard"
    minimum = [task for task in tasks if task.minimum_required]
    if minimum_mode and minimum and all(done(task) for task in minimum):
        return "minimum"
    return "incomplete"


# Each completed task earns sunlight. Total obtainable sunlight is the task count times this value,
# so a plan that is fully completed always has enough sunlight to grow its sunflower all the way.
TASK_REWARD = 10
# Growth stages as a share of the plan's total task sunlight. "盛开" only applies once a plan is completed.
PLANT_STAGE_RATIOS = (("发芽", 0.05), ("幼苗", 0.20), ("长叶", 0.50), ("花苞", 0.80))


def plant_total_sunlight(task_count):
    return TASK_REWARD * max(1, int(task_count))


def plant_stage_from_fed(fed_sunlight, total_sunlight):
    if total_sunlight <= 0:
        return "种子"
    ratio = fed_sunlight / total_sunlight
    stage = "种子"
    for name, threshold in PLANT_STAGE_RATIOS:
        if ratio + 1e-9 >= threshold:
            stage = name
    return stage


def peak_seed_fed(peak, total_sunlight):
    """Map legacy plant_peak (standard-day milestone) to a feed amount so existing plants do not regress."""
    if peak >= 7:
        ratio = 0.8
    elif peak >= 5:
        ratio = 0.5
    elif peak >= 3:
        ratio = 0.2
    elif peak >= 1:
        ratio = 0.05
    else:
        ratio = 0.0
    return round(total_sunlight * ratio)


class StudyGrowth:
    def __init__(self, study):
        self.study = study
        StudyReview(study)
        with study.repository._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS study_growth_settings (
                    plan_id TEXT PRIMARY KEY REFERENCES study_plans(id) ON DELETE CASCADE,
                    enabled_at TEXT NOT NULL, settings_json TEXT NOT NULL, plant_peak INTEGER NOT NULL DEFAULT 0, baseline_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS study_day_modes (
                    plan_id TEXT NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
                    local_date TEXT NOT NULL, minimum_mode INTEGER NOT NULL,
                    PRIMARY KEY(plan_id,local_date)
                );
                CREATE TABLE IF NOT EXISTS study_flex_history (
                    plan_id TEXT NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
                    request_id TEXT NOT NULL, task_id TEXT NOT NULL, slot_json TEXT NOT NULL,
                    old_date TEXT NOT NULL, new_date TEXT NOT NULL, minutes INTEGER NOT NULL,
                    active INTEGER NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(plan_id,request_id)
                );
                CREATE TABLE IF NOT EXISTS study_reward_balances (
                    source TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES study_plans(id) ON DELETE CASCADE,
                    amount INTEGER NOT NULL, effective_date TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS study_reward_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id TEXT NOT NULL,
                    source TEXT NOT NULL, amount INTEGER NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS study_reward_plan ON study_reward_ledger(plan_id,id);
                CREATE TABLE IF NOT EXISTS study_growth_fed (
                    plan_id TEXT PRIMARY KEY REFERENCES study_plans(id) ON DELETE CASCADE,
                    fed_sunlight INTEGER NOT NULL DEFAULT 0
                );
            """)
            # One-time migration: seed existing plants from their legacy standard-day peak so they do not regress.
            for row in db.execute("SELECT plan_id, plant_peak FROM study_growth_settings"):
                if not db.execute("SELECT 1 FROM study_growth_fed WHERE plan_id=?", (row["plan_id"],)).fetchone():
                    count = db.execute("SELECT COUNT(*) FROM study_tasks WHERE plan_id=?", (row["plan_id"],)).fetchone()[0]
                    db.execute("INSERT INTO study_growth_fed(plan_id, fed_sunlight) VALUES (?,?)",
                               (row["plan_id"], peak_seed_fed(row["plant_peak"], plant_total_sunlight(count))))

    def settings(self, plan_id):
        self.study.get_plan(plan_id)
        with self.study.repository._connect() as db:
            row = db.execute("SELECT * FROM study_growth_settings WHERE plan_id=?", (plan_id,)).fetchone()
        return dict(row) if row else None

    def enable(self, plan_id, payload):
        plan = self.study.get_plan(plan_id)
        if plan.status.value in {"completed","archived"}:
            raise ValueError("已结束计划只能查看成长记录。")
        settings = GrowthSettings.model_validate(payload)
        ZoneInfo(settings.timezone)
        with self.study.repository._connect() as db:
            baseline={row["task_id"]:row["revision"] for row in db.execute(
                "SELECT e.task_id,e.revision FROM study_task_completion_events e JOIN study_tasks t ON t.id=e.task_id WHERE t.plan_id=?",(plan_id,))}
            db.execute(
                "INSERT INTO study_growth_settings(plan_id,enabled_at,settings_json,baseline_json) VALUES (?,?,?,?) "
                "ON CONFLICT(plan_id) DO UPDATE SET settings_json=excluded.settings_json",
                (plan_id, self.study._now().isoformat(), settings.model_dump_json(),json.dumps(baseline)),
            )
            local_date=self.study._now().astimezone(ZoneInfo(settings.timezone)).date().isoformat()
            db.execute("INSERT INTO study_day_modes VALUES (?,?,?) "
                       "ON CONFLICT(plan_id,local_date) DO UPDATE SET minimum_mode=excluded.minimum_mode",
                       (plan_id,local_date,int(settings.minimum_mode)))
        return self.state(plan_id)

    def feed(self, plan_id, amount):
        """Spend available sunlight to grow the plan's sunflower."""
        plan = self.study.get_plan(plan_id)
        if not self.settings(plan_id):
            raise ValueError("请先启用本计划的成长记录。")
        if plan.status.value in {"completed", "archived"}:
            raise ValueError("已结束计划不能再喂食。")
        with self.study.repository._connect() as db:
            closed = None
            if db.execute("SELECT name FROM sqlite_master WHERE name='study_plan_closures'").fetchone():
                closed = db.execute("SELECT 1 FROM study_plan_closures WHERE plan_id=?", (plan_id,)).fetchone()
        if closed:
            raise ValueError("已结束计划不能再喂食。")
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            raise ValueError("喂食数量须为正整数。")
        if amount <= 0:
            raise ValueError("喂食数量须大于0。")
        # Reconcile rewards before computing the spendable balance.
        self.state(plan_id)
        with self.study.repository._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            earned = db.execute(
                "SELECT COALESCE(SUM(amount),0) FROM study_reward_ledger WHERE plan_id=?", (plan_id,)).fetchone()[0]
            fed_row = db.execute("SELECT fed_sunlight FROM study_growth_fed WHERE plan_id=?", (plan_id,)).fetchone()
            fed = fed_row["fed_sunlight"] if fed_row else 0
            available = earned - fed
            if amount > available:
                raise ValueError(f"阳光不足，当前可喂 {max(0, available)} 点。")
            total = plant_total_sunlight(len(plan.tasks))
            remaining = max(0, total - fed)
            if remaining <= 0:
                raise ValueError("这株向日葵已经长满了，计划完成后就会盛开并移栽。")
            fed += min(amount, remaining)
            db.execute("INSERT INTO study_growth_fed(plan_id,fed_sunlight) VALUES (?,?) "
                       "ON CONFLICT(plan_id) DO UPDATE SET fed_sunlight=excluded.fed_sunlight", (plan_id, fed))
        return self.state(plan_id)

    def flex_preview(self, plan_id, task_id, slot_id):
        original = self.study.get_plan(plan_id)
        plan = original.model_copy(deep=True)
        task = next((task for task in plan.tasks if task.id == task_id), None)
        slot = next((slot for slot in plan.flex_slots if slot.id == slot_id), None)
        if not task or not slot:
            raise ValueError("请选择本计划中的任务和机动槽。")
        if task.scheduled_date == slot.scheduled_date:
            raise ValueError("任务已经安排在该机动日期。")
        if task.status is StudyTaskStatus.COMPLETED:
            raise ValueError("已完成任务不能消耗机动时间。")
        if slot.planned_minutes < task.planned_minutes:
            raise ValueError("机动时间不足。")
        task.scheduled_date = slot.scheduled_date
        task.updated_at = self.study._now()
        if slot.planned_minutes == task.planned_minutes:
            plan.flex_slots.remove(slot)
        else:
            slot.planned_minutes -= task.planned_minutes
        from .validation import validate_study_plan
        return original, validate_study_plan(plan)

    def use_flex(self, plan_id, task_id, slot_id, request_id, expected_updated_at):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("缺少机动操作编号。")
        with self.study.repository._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT * FROM study_flex_history WHERE plan_id=? AND request_id=?", (plan_id, request_id),
            ).fetchone()
            if previous:
                if previous["task_id"] != task_id or json.loads(previous["slot_json"])["id"] != slot_id:
                    raise ValueError("操作编号已用于其他调整。")
            else:
                original, plan = self.flex_preview(plan_id, task_id, slot_id)
                task = next(task for task in original.tasks if task.id == task_id)
                slot = next(slot for slot in original.flex_slots if slot.id == slot_id)
                self.study.save_plan_definition(plan, expected_updated_at=expected_updated_at, connection=db)
                db.execute("INSERT INTO study_flex_history VALUES (?,?,?,?,?,?,?,?,?)", (
                    plan_id, request_id, task_id, slot.model_dump_json(),
                    task.scheduled_date.isoformat(), slot.scheduled_date.isoformat(),
                    task.planned_minutes, 1, self.study._now().isoformat(),
                ))
        saved = self.study.get_plan(plan_id)
        if not previous:
            from .reminders import sync_plan_reminders
            sync_plan_reminders(self.study, saved, original)
        return saved

    def undo_flex(self, plan_id, request_id, expected_updated_at):
        with self.study.repository._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM study_flex_history WHERE plan_id=? AND request_id=?",
                             (plan_id, request_id)).fetchone()
            if row is None:
                raise KeyError(request_id)
            if not row["active"]:
                return self.study.get_plan(plan_id)
            original = self.study.get_plan(plan_id)
            plan = original.model_copy(deep=True)
            task = next((item for item in plan.tasks if item.id == row["task_id"]), None)
            if not task or task.status is StudyTaskStatus.COMPLETED or task.scheduled_date.isoformat() != row["new_date"] or task.planned_minutes != row["minutes"]:
                raise ValueError("任务已变化，请先核对计划后再调整。")
            task.scheduled_date = date.fromisoformat(row["old_date"])
            slot = StudyFlexSlot.model_validate_json(row["slot_json"])
            current = next((item for item in plan.flex_slots if item.id == slot.id), None)
            if current:
                if current.scheduled_date != slot.scheduled_date:
                    raise ValueError("机动槽日期已修改，请先核对计划。")
                current.planned_minutes += row["minutes"]
            else:
                slot.planned_minutes = row["minutes"]
                plan.flex_slots.append(slot)
            self.study.save_plan_definition(plan, expected_updated_at=expected_updated_at, connection=db)
            db.execute("UPDATE study_flex_history SET active=0 WHERE plan_id=? AND request_id=?", (plan_id, request_id))
        saved = self.study.get_plan(plan_id)
        from .reminders import sync_plan_reminders
        sync_plan_reminders(self.study, saved, original)
        return saved

    def recovery(self, plan_id, target_date):
        plan = self.study.get_plan(plan_id)
        target = date.fromisoformat(target_date)
        if not plan.start_date <= target <= plan.end_date:
            raise ValueError("恢复日期须位于计划日期范围内。")
        pending = sorted((task for task in plan.tasks
                          if task.scheduled_date < target and task.status not in {StudyTaskStatus.COMPLETED,StudyTaskStatus.SKIPPED}),
                         key=lambda task: ({"must": 0, "standard": 1, "optional": 2}[task.priority],
                                           task.scheduled_date, task.order_index))[:3]
        patch = plan.model_copy(deep=True)
        selected = {task.id for task in pending}
        for task in patch.tasks:
            if task.id in selected:
                task.scheduled_date = target
        from .markdown import export_study_plan_markdown
        return {"markdown": export_study_plan_markdown(patch), "task_ids": list(selected),
                "capacity": self.study.plan_capacity(patch), "expected_updated_at": plan.updated_at.isoformat()}

    def facts(self, plan_id, local_date, zone_name):
        plan = self.study.get_plan(plan_id)
        day = date.fromisoformat(local_date)
        zone = ZoneInfo(zone_name)
        start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
        tasks = [task for task in plan.tasks if task.scheduled_date == day]
        with self.study.repository._connect() as db:
            sessions = db.execute(
                "SELECT s.* FROM study_sessions s JOIN study_tasks t ON t.id=s.task_id "
                "WHERE t.plan_id=? AND s.status='completed' AND s.session_type='focus' "
                "AND s.started_at IS NOT NULL AND s.ended_at IS NOT NULL", (plan_id,),
            ).fetchall()
            attempts = db.execute(
                "SELECT e.* FROM study_learning_attempts e JOIN study_activity_attribution a "
                "ON a.event_id=e.id AND a.kind='attempt' WHERE a.plan_id=? AND e.created_at>=? AND e.created_at<?",
                (plan_id, start.isoformat(), end.isoformat()),
            ).fetchall()
            recalls = db.execute(
                "SELECT e.* FROM study_learning_recalls e JOIN study_activity_attribution a "
                "ON a.event_id=e.id AND a.kind='recall' WHERE a.plan_id=? AND e.created_at>=? AND e.created_at<?",
                (plan_id, start.isoformat(), end.isoformat()),
            ).fetchall()
            flex = db.execute(
                "SELECT request_id,minutes FROM study_flex_history WHERE plan_id=? AND new_date=? AND active=1",
                (plan_id, local_date),
            ).fetchall()
        focus = 0.0
        focus_sources = []
        for session in sessions:
            began, ended = datetime.fromisoformat(session["started_at"]), datetime.fromisoformat(session["ended_at"])
            wall = (ended - began).total_seconds()
            overlap = max(0, (min(ended, end) - max(began, start)).total_seconds())
            if wall > 0 and overlap > 0:
                focus_sources.append(session["id"])
                focus += min(wall, session["actual_minutes"] * 60) * overlap / wall / 60
        setting = self.settings(plan_id)
        with self.study.repository._connect() as db:
            mode=db.execute("SELECT minimum_mode FROM study_day_modes WHERE plan_id=? AND local_date=?",(plan_id,local_date)).fetchone()
        minimum=bool(mode and mode["minimum_mode"])
        return {
            "plan_id": plan_id, "date": local_date, "timezone": zone_name, "projection_version": 1,
            "tasks": len(tasks), "completed": sum(task.status is StudyTaskStatus.COMPLETED for task in tasks),
            "level": day_level(tasks, minimum), "focus_minutes": round(focus, 2),
            "attempts": len(attempts), "correct": sum(row["correct"] for row in attempts),
            "wrong_answers":len(attempts)-sum(row["correct"] for row in attempts),
            "recalls": len(recalls), "mastered": sum(row["rating"] == 2 for row in recalls),
            "flex_minutes": sum(row["minutes"] for row in flex),
            "flex_reserved_minutes":sum(slot.planned_minutes for slot in plan.flex_slots if slot.scheduled_date==day),
            "sources": {"tasks": [task.id for task in tasks], "attempts": [row["id"] for row in attempts],
                        "recalls": [row["id"] for row in recalls], "focus": focus_sources, "flex": [row["request_id"] for row in flex]},
        }

    def state(self, plan_id):
        plan = self.study.get_plan(plan_id)
        setting = self.settings(plan_id)
        final_summary = None
        with self.study.repository._connect() as db:
            if db.execute("SELECT name FROM sqlite_master WHERE name='study_plan_closures'").fetchone():
                closed = db.execute("SELECT summary FROM study_plan_closures WHERE plan_id=?",(plan_id,)).fetchone()
                final_summary = closed["summary"] if closed else None
        if not setting:
            return {"enabled": False, "sunlight": 0, "available_sunlight": 0, "fed_sunlight": 0,
                    "plant": "种子", "days": [], "plan_id": plan_id, "final_summary": final_summary}
        config = GrowthSettings.model_validate_json(setting["settings_json"])
        zone = ZoneInfo(config.timezone)
        today = self.study._now().astimezone(zone).date()
        with self.study.repository._connect() as db:
            mode=db.execute("SELECT minimum_mode FROM study_day_modes WHERE plan_id=? AND local_date=?",(plan_id,today.isoformat())).fetchone()
        config.minimum_mode=bool(mode and mode["minimum_mode"])
        enabled = datetime.fromisoformat(setting["enabled_at"])
        first = max(plan.start_date, enabled.astimezone(zone).date())
        dates = {task.scheduled_date for task in plan.tasks if first <= task.scheduled_date <= today}
        with self.study.repository._connect() as db:
            for kind, table in (("attempt", "study_learning_attempts"), ("recall", "study_learning_recalls")):
                for row in db.execute(
                    f"SELECT e.created_at FROM {table} e JOIN study_activity_attribution a "
                    "ON a.event_id=e.id AND a.kind=? WHERE a.plan_id=?", (kind, plan_id),
                ):
                    day = datetime.fromisoformat(row["created_at"]).astimezone(zone).date()
                    if first <= day <= today:
                        dates.add(day)
        dates = sorted(dates)
        days = [self.facts(plan_id, day.isoformat(), config.timezone) for day in dates]
        with self.study.repository._connect() as db:
            baseline=json.loads(setting["baseline_json"])
            completed_ids={row["task_id"] for row in db.execute(
                "SELECT e.task_id,e.revision FROM study_task_completion_events e JOIN study_tasks t ON t.id=e.task_id "
                "WHERE t.plan_id=? AND e.active=1",(plan_id,))
                if row["revision"]>baseline.get(row["task_id"],0)}
        eligible_dates={task.scheduled_date.isoformat() for task in plan.tasks if task.id in completed_ids}
        standard = sum(day["level"] in {"standard", "full"} and day["date"] in eligible_dates for day in days)
        desired = {}
        source_dates = {}
        for day in days:
            day["reward_eligible"] = day["date"] in eligible_dates
        for day in days:
            if day["level"] in {"standard", "full"} and day["date"] in eligible_dates:
                desired[f"daily:{plan_id}:{day['date']}"] = config.daily_rewards[
                    hashlib.sha256(day["date"].encode()).digest()[0] % 3]
                source_dates[f"daily:{plan_id}:{day['date']}"] = day["date"]
        if standard >= 3:
            desired[f"stage:{plan_id}:3"] = 60
            source_dates[f"stage:{plan_id}:3"] = [day["date"] for day in days if day["level"] in {"standard","full"} and day["reward_eligible"]][2]
        seventh = plan.start_date + timedelta(days=6)
        if standard >= 5 and any(day["date"] == seventh.isoformat() and day["level"] in {"standard", "full"} and day["reward_eligible"] for day in days):
            desired[f"stage:{plan_id}:7"] = 120
            source_dates[f"stage:{plan_id}:7"] = seventh.isoformat()
        # Task completion is the primary sunlight source: one reward per completed task revision.
        total = plant_total_sunlight(len(plan.tasks))
        with self.study.repository._connect() as db:
            completed_events = [(row["task_id"], row["revision"], row["completed_at"]) for row in db.execute(
                "SELECT e.task_id,e.revision,e.completed_at FROM study_task_completion_events e JOIN study_tasks t ON t.id=e.task_id "
                "WHERE t.plan_id=? AND e.active=1", (plan_id,))]
        for task_id, revision, completed_at in completed_events:
            if revision > baseline.get(task_id, 0):
                source = f"task:{plan_id}:{task_id}:{revision}"
                desired[source] = TASK_REWARD
                source_dates[source] = datetime.fromisoformat(completed_at).astimezone(zone).date().isoformat()
        now = self.study._now().isoformat()
        with self.study.repository._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for kind, table in (("attempt", "study_learning_attempts"), ("recall", "study_learning_recalls")):
                for row in db.execute(
                    f"SELECT e.id,e.created_at FROM {table} e JOIN study_activity_attribution a "
                    "ON a.event_id=e.id AND a.kind=? WHERE a.plan_id=? AND e.created_at>=?",
                    (kind, plan_id, enabled.isoformat()),
                ):
                    desired[kind + ":" + row["id"]] = config.practice_points
                    source_dates[kind + ":" + row["id"]] = datetime.fromisoformat(row["created_at"]).astimezone(zone).date().isoformat()
            for row in db.execute(
                "SELECT s.id,s.actual_minutes,s.ended_at FROM study_sessions s JOIN study_tasks t ON t.id=s.task_id "
                "WHERE t.plan_id=? AND s.status='completed' AND s.session_type='focus' AND s.ended_at>=?",
                (plan_id, enabled.isoformat()),
            ):
                desired["focus:" + row["id"]] = row["actual_minutes"] // 25 * config.focus_block_points
                source_dates["focus:" + row["id"]] = datetime.fromisoformat(row["ended_at"]).astimezone(zone).date().isoformat()
            prior = {row["source"]: row["amount"] for row in db.execute(
                "SELECT source,amount FROM study_reward_balances WHERE plan_id=?", (plan_id,))}
            for source in prior.keys() | desired.keys():
                amount = desired.get(source, 0)
                row = db.execute("SELECT * FROM study_reward_balances WHERE source=?", (source,)).fetchone()
                if row and row["plan_id"] != plan_id:
                    db.execute("INSERT INTO study_reward_ledger(plan_id,source,amount,created_at) VALUES (?,?,?,?)",
                               (row["plan_id"], source, -row["amount"], now))
                    old = 0
                else:
                    old = row["amount"] if row else 0
                if amount != old:
                    db.execute("INSERT INTO study_reward_ledger(plan_id,source,amount,created_at) VALUES (?,?,?,?)",
                               (plan_id, source, amount - old, now))
                db.execute(
                    "INSERT INTO study_reward_balances VALUES (?,?,?,?) "
                    "ON CONFLICT(source) DO UPDATE SET plan_id=excluded.plan_id,amount=excluded.amount,effective_date=excluded.effective_date",
                    (source, plan_id, amount, source_dates.get(source, row["effective_date"] if row else today.isoformat())),
                )
            db.execute("UPDATE study_growth_settings SET plant_peak=MAX(plant_peak,?) WHERE plan_id=?", (standard, plan_id))
            sunlight = db.execute("SELECT COALESCE(SUM(amount),0) FROM study_reward_ledger WHERE plan_id=?", (plan_id,)).fetchone()[0]
            peak = db.execute("SELECT plant_peak FROM study_growth_settings WHERE plan_id=?", (plan_id,)).fetchone()[0]
            fed_row = db.execute("SELECT fed_sunlight FROM study_growth_fed WHERE plan_id=?", (plan_id,)).fetchone()
            fed = fed_row["fed_sunlight"] if fed_row else 0
            history = [dict(row) for row in db.execute(
                "SELECT * FROM study_flex_history WHERE plan_id=? ORDER BY created_at DESC", (plan_id,))]
        plant = plant_stage_from_fed(fed, total)
        momentum = 0
        for day in days:
            if day["level"] in {"standard", "full"}:
                momentum += 1
            elif day["level"] == "incomplete":
                momentum = max(0, momentum - 1)
        return {"enabled": True, "plan_id": plan_id, "sunlight": sunlight,
                "available_sunlight": max(0, sunlight - fed), "fed_sunlight": fed,
                "plant_total": total, "plant_progress": round(min(1.0, fed / total), 4) if total else 0.0,
                "feedable_sunlight": max(0, min(sunlight - fed, total - fed)),
                "final_summary": final_summary, "plant": plant,
                "standard_days": standard, "momentum": momentum, "days": days,
                "settings": config.model_dump(), "history": history}
