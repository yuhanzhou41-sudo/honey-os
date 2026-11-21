"""Per-plan Study reminders delivered as Windows system notifications.

Each plan owns its own reminder settings (mode + explicit times). When a slot
comes due, the reminder text is produced by the on-device Qwen model from the
day's real facts, with the tone escalating from relaxed to urgent as more
reminders are delivered that day. Every delivered reminder is recorded so the
UI can show how many nudges a plan needed before it was finished.
"""

import asyncio
from datetime import date, datetime, time as clock_time, timedelta
import json
import logging
import re
from threading import RLock
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import notify
from .learning import StudyLearningMemory
from .service import StudyService

logger = logging.getLogger(__name__)

_TIME = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
MAX_TIMES = 6
CATCH_UP = timedelta(minutes=15)
TONES = ("轻松", "紧张", "急迫")

MODES = {
    "gentle": {"label": "轻度", "times": ["20:00"]},
    "standard": {"label": "标准", "times": ["18:00", "21:00"]},
    "strong": {"label": "强化", "times": ["12:00", "18:00", "21:30"]},
    "custom": {"label": "自定义", "times": []},
}

_OPENERS = ("可以", "建议", "先", "试着", "记得", "喂", "别", "该", "现在", "今天", "再", "还剩")
_FORBIDDEN = re.compile(
    r"[0-9一二三四五六七八九十百千万两〇零]|MEDIA:|已完成|已掌握|授权|奖励|惩罚|隐私|自杀|死"
)
_SYSTEM_PROMPTS = {
    0: (
        "你在提醒朋友学习。语气轻松、口语化、有生活感，像熟人随口催一句，不说教。"
        "只根据 JSON 事实给一句建议，40字内。开头用：可以、建议、先、试着、记得、别。"
        "不要写数字，不要声称任务已完成，不要提奖励或授权。只返回 JSON：{\"advice\":\"...\"}"
    ),
    1: (
        "你在提醒朋友学习。语气明显着急、催促，但尊重对方，像担心他拖到太晚。"
        "只根据 JSON 事实给一句建议，40字内。开头用：先、别、该、现在、今天、再、还剩、记得。"
        "不要写数字，不要声称任务已完成，不要提奖励或授权。只返回 JSON：{\"advice\":\"...\"}"
    ),
    2: (
        "你在提醒朋友学习。语气急迫，可以半开玩笑地施压，例如说再拖下去明天会更难受。"
        "只根据 JSON 事实给一句建议，40字内。开头用：喂、别、再、现在、今天、先、该、还剩。"
        "不能侮辱人，不能提人身安全、惩罚或隐私。不要写数字，不要声称任务已完成。"
        "只返回 JSON：{\"advice\":\"...\"}"
    ),
}
_FALLBACKS = {
    (0, "not_started"): "先挑一件最简单的内容开始，二十分钟就够。",
    (0, "pending"): "已经做了一部分，把剩下的一小步收掉就轻松了。",
    (0, "overloaded"): "今天的量有点满，先保住最小的那个目标。",
    (1, "not_started"): "今天还没开始，时间在走，先打开资料吧。",
    (1, "pending"): "剩下的别留到晚上，现在补一段就稳了。",
    (1, "overloaded"): "时间不够了，先把可选内容砍掉，保住主体。",
    (2, "not_started"): "今天一项都还没动，再拖下去明天就要加倍还。",
    (2, "pending"): "再磨蹭就要熬夜了，现在把剩下的收掉。",
    (2, "overloaded"): "今晚会很难看，先砍掉可选项，立刻做保底。",
}


class ReminderSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, strict=True)
    mode: str = "standard"
    times: list[str] = Field(default_factory=list)
    timezone: str = "Asia/Shanghai"

    @model_validator(mode="after")
    def validate_settings(self):
        try:
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise ValueError("时区无效。") from exc
        if self.mode not in MODES:
            raise ValueError("请选择有效的提醒模式。")
        if self.mode == "custom" and not self.times:
            raise ValueError("自定义模式请至少添加一个提醒时间。")
        if len(self.times) > MAX_TIMES:
            raise ValueError(f"每天最多设置 {MAX_TIMES} 次提醒。")
        if any(not _TIME.fullmatch(value) for value in self.times):
            raise ValueError("提醒时间格式应为 HH:MM。")
        return self

    def effective_times(self):
        if self.times:
            return sorted(set(self.times))
        return list(MODES[self.mode]["times"])


def _day(value):
    return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(str(value))


class StudyReminders:
    def __init__(self, study):
        self.study = study
        self.memory = StudyLearningMemory(study)
        self._lock = RLock()
        with study.repository._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS study_plan_reminders (
                    plan_id TEXT PRIMARY KEY,
                    settings_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS study_plan_reminder_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plan_id TEXT NOT NULL,
                    local_date TEXT NOT NULL,
                    slot TEXT NOT NULL,
                    tone INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(plan_id, local_date, slot)
                );
            """)

    def settings(self, plan_id):
        self.study.get_plan(plan_id)
        with self.study.repository._connect() as db:
            row = db.execute(
                "SELECT settings_json FROM study_plan_reminders WHERE plan_id=?", (plan_id,)
            ).fetchone()
        return ReminderSettings.model_validate_json(row[0]) if row else ReminderSettings()

    def configure(self, plan_id, payload):
        self.study.get_plan(plan_id)
        settings = ReminderSettings.model_validate(payload)
        settings = settings.model_copy(update={"times": settings.effective_times()})
        with self.study.repository._connect() as db, db:
            db.execute(
                "INSERT INTO study_plan_reminders VALUES (?,?,?) "
                "ON CONFLICT(plan_id) DO UPDATE SET settings_json=excluded.settings_json,"
                "updated_at=excluded.updated_at",
                (plan_id, settings.model_dump_json(), self.study._now().isoformat()),
            )
        return self.summary(plan_id)

    def summary(self, plan_id):
        settings = self.settings(plan_id)
        local = self.study._now().astimezone(ZoneInfo(settings.timezone))
        today = local.date().isoformat()
        with self.study.repository._connect() as db:
            total = db.execute(
                "SELECT COUNT(*) FROM study_plan_reminder_events WHERE plan_id=?", (plan_id,)
            ).fetchone()[0]
            today_count = db.execute(
                "SELECT COUNT(*) FROM study_plan_reminder_events "
                "WHERE plan_id=? AND local_date=?", (plan_id, today),
            ).fetchone()[0]
        return {
            "settings": settings.model_dump(),
            "presets": MODES,
            "sent_total": int(total),
            "sent_today": int(today_count),
        }

    def facts(self, plan_id, now):
        settings = self.settings(plan_id)
        if not settings.enabled:
            return None
        plan = self.study.get_plan(plan_id)
        if plan.status.value != "active":
            return None
        local = now.astimezone(ZoneInfo(settings.timezone))
        today = local.date()
        if not (_day(plan.start_date) <= today <= _day(plan.end_date)):
            return None
        tasks = [task for task in plan.tasks if _day(task.scheduled_date) == today]
        if not tasks:
            return None
        done = [task for task in tasks if task.status.value == "completed"]
        if len(done) == len(tasks):
            return None
        remaining = [
            task for task in tasks
            if task.status.value not in {"completed", "skipped", "cancelled"}
        ]
        minutes = sum(task.planned_minutes for task in remaining)
        boundary = datetime.combine(today, clock_time(23, 0), tzinfo=local.tzinfo)
        overloaded = minutes > max(0, (boundary - local).total_seconds() / 60)
        kind = "not_started" if not done else ("overloaded" if overloaded else "pending")
        return {
            "plan_id": plan_id,
            "title": plan.title,
            "date": today.isoformat(),
            "tasks": len(tasks),
            "completed": len(done),
            "remaining_minutes": minutes,
            "next_task": remaining[0].title if remaining else "",
            "kind": kind,
        }

    def message(self, facts, tone):
        tone = max(0, min(int(tone), 2))
        fallback = _FALLBACKS.get((tone, facts["kind"])) or _FALLBACKS[(0, "pending")]
        advice = fallback
        try:
            from .local_model import _generate

            raw = _generate(
                _SYSTEM_PROMPTS[tone],
                json.dumps(facts, ensure_ascii=False),
                task="学习提醒", max_tokens=120, timeout=15,
            )
            result = json.loads(raw)
            value = result.get("advice")
            if (
                set(result) == {"advice"}
                and isinstance(value, str) and value.strip()
                and len(value) <= 40
                and value.startswith(_OPENERS)
                and not _FORBIDDEN.search(value)
            ):
                advice = value.strip()
        except Exception:
            # Local model missing/busy/bad JSON must never block the reminder.
            pass
        prefix = f"今天 {facts['completed']}/{facts['tasks']} 项完成"
        return f"{prefix}，{advice}"[:120]

    def run_due(self, now):
        if not notify.available():
            return 0
        sent = 0
        with self._lock:
            for plan in self.study.list_plans():
                try:
                    sent += self._run_plan(plan.id, now)
                except Exception:
                    logger.exception("Study reminder failed for plan %s", plan.id)
        return sent

    def _run_plan(self, plan_id, now):
        settings = self.settings(plan_id)
        if not settings.enabled:
            return 0
        facts = self.facts(plan_id, now)
        if facts is None:
            return 0
        local = now.astimezone(ZoneInfo(settings.timezone))
        for slot in settings.effective_times():
            slot_at = datetime.combine(local.date(), clock_time.fromisoformat(slot), tzinfo=local.tzinfo)
            if not (slot_at <= local <= slot_at + CATCH_UP):
                continue
            with self.study.repository._connect() as db:
                exists = db.execute(
                    "SELECT 1 FROM study_plan_reminder_events "
                    "WHERE plan_id=? AND local_date=? AND slot=?",
                    (plan_id, local.date().isoformat(), slot),
                ).fetchone()
                count = db.execute(
                    "SELECT COUNT(*) FROM study_plan_reminder_events "
                    "WHERE plan_id=? AND local_date=?",
                    (plan_id, local.date().isoformat()),
                ).fetchone()[0]
            if exists:
                continue
            text = self.message(facts, min(int(count), 2))
            title = f"该学习了 · {facts['title']}"[:60]
            if not notify.send(title, text):
                logger.warning("Study reminder for plan %s could not be shown", plan_id)
                return 0
            with self.study.repository._connect() as db, db:
                db.execute(
                    "INSERT OR IGNORE INTO study_plan_reminder_events "
                    "(plan_id,local_date,slot,tone,message,channel,created_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (plan_id, local.date().isoformat(), slot, min(int(count), 2), text,
                     "toast", now.isoformat()),
                )
            return 1
        return 0


async def run_study_maintenance(runner, now):
    from honeyos.core.constants import get_honeyos_home
    from honeyos.companion.work_mode import active_work

    if not (get_honeyos_home() / "study/study.db").exists():
        return
    try:
        store = await asyncio.to_thread(lambda: StudyReminders(StudyService()))
        await asyncio.to_thread(store.memory.maintain)
        if await asyncio.to_thread(active_work):
            return
        await asyncio.to_thread(store.run_due, now)
    except Exception:
        logger.exception("Study reminders will retry on the next scheduler tick")
