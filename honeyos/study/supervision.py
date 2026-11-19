"""Opt-in, daily-limited Study supervision through the existing web channel."""
import asyncio
from datetime import datetime, time, timedelta
import hashlib
import json
import logging
import re
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .learning import StudyLearningMemory
from .service import StudyService

logger=logging.getLogger(__name__)


class SupervisionSettings(BaseModel):
    model_config=ConfigDict(extra="forbid")
    enabled: bool=Field(default=False,strict=True)
    timezone: str="Asia/Shanghai"
    quiet_start: int=Field(default=22,ge=0,le=23)
    quiet_end: int=Field(default=8,ge=0,le=23)
    remind_hour: int=Field(default=18,ge=0,le=23)
    session_id: str=""

    @model_validator(mode="after")
    def validate_settings(self):
        ZoneInfo(self.timezone)
        if self.quiet_start==self.quiet_end:
            raise ValueError("安静时段的开始和结束须不同。")
        if self.enabled and not self.session_id.strip():
            raise ValueError("请先打开聊天会话。")
        return self


class StudySupervision:
    def __init__(self,study):
        self.study=study
        self.memory=StudyLearningMemory(study)
        with study.repository._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS study_supervision_settings (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),settings_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS study_supervision_deliveries (
                    local_date TEXT PRIMARY KEY,delivery_id TEXT NOT NULL UNIQUE,
                    message TEXT NOT NULL,facts_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL
                );
            """)

    def settings(self):
        with self.study.repository._connect() as db:
            row=db.execute("SELECT settings_json FROM study_supervision_settings WHERE singleton=1").fetchone()
        return SupervisionSettings.model_validate_json(row[0]) if row else SupervisionSettings()

    def configure(self,payload):
        settings=SupervisionSettings.model_validate(payload)
        with self.study.repository._connect() as db:
            db.execute("INSERT INTO study_supervision_settings VALUES (1,?) "
                       "ON CONFLICT(singleton) DO UPDATE SET settings_json=excluded.settings_json",
                       (settings.model_dump_json(),))
        return settings.model_dump()

    def facts(self,now):
        settings=self.settings()
        local=now.astimezone(ZoneInfo(settings.timezone))
        quiet=(settings.quiet_start<=local.hour<settings.quiet_end) if settings.quiet_start<settings.quiet_end else (
            local.hour>=settings.quiet_start or local.hour<settings.quiet_end)
        if not settings.enabled or quiet or local.hour<settings.remind_hour:
            return None
        with self.study.repository._connect() as db:
            if db.execute("SELECT id FROM study_sessions WHERE status='running' LIMIT 1").fetchone():
                return None
        snapshots=[]
        for plan in self.study.list_plans():
            if plan.status.value=="active" and self.memory.growth.settings(plan.id):
                snapshots.append(self.memory.growth.facts(plan.id,local.date().isoformat(),settings.timezone))
        total=sum(item["tasks"] for item in snapshots)
        with self.study.repository._connect() as db:
            monday=(local.date()-timedelta(days=local.weekday())).isoformat()
            weekly_ready=local.weekday()==0 and db.execute(
                "SELECT w.plan_id FROM study_weekly_reports w JOIN study_plans p ON p.id=w.plan_id "
                "JOIN study_growth_settings g ON g.plan_id=p.id WHERE p.status='active' AND w.week_start=? LIMIT 1",
                ((local.date()-timedelta(days=local.weekday()+7)).isoformat(),)).fetchone() is not None
        if total==0 and not weekly_ready:
            return None
        completed=sum(item["completed"] for item in snapshots)
        focus=round(sum(item["focus_minutes"] for item in snapshots),1)
        remaining=sum(task.planned_minutes for plan in self.study.list_plans() if plan.id in {item["plan_id"] for item in snapshots}
                      for task in plan.tasks if task.scheduled_date==local.date() and task.status.value!="completed")
        boundary=datetime.combine(local.date(),time(settings.quiet_start),local.tzinfo)
        if boundary<=local:
            boundary+=timedelta(days=1)
        overloaded=remaining>max(0,(boundary-local).total_seconds()/60)
        kind=("weekly_ready" if total==0 else "completed" if completed==total else "overloaded" if overloaded
              else "not_started" if completed==0 and focus==0 else "pending")
        return {"date":local.date().isoformat(),"kind":kind,"tasks":total,"completed":completed,
                "focus_minutes":focus,"plan_ids":[item["plan_id"] for item in snapshots]}

    def message(self,facts):
        from .local_model import _generate
        fallback={"completed":"今天的目标已完成，可以好好休息。","not_started":"先选最重要的内容开始。",
                  "pending":"可以从剩余内容里选最重要的部分。",
                  "overloaded":"建议先完成保底内容，再确认延期安排。","weekly_ready":"可以查看周报，再安排接下来的学习。"}
        advice=fallback[facts["kind"]]
        try:
            raw=_generate(
                "只根据JSON事实返回JSON，字段kind须原样保留，advice为40字内建议，"
                "以可以、建议、先、试着或记得开头，不写任何数字、不声明已完成或改变设置。",
                json.dumps(facts,ensure_ascii=False),task="学习监督",max_tokens=160,timeout=20)
            result=json.loads(raw)
            value=result.get("advice")
            if (set(result)=={"kind","advice"} and result["kind"]==facts["kind"]
                and isinstance(value,str) and len(value)<=40
                and value.startswith(("可以","建议","先","试着","记得"))
                and not re.search(r"[0-9一二三四五六七八九十百千万两〇零]|MEDIA:|已完成|已掌握|授权|奖励",value)):
                advice=value
        except (ValueError,TypeError,AttributeError):
            pass
        prefix="学习周报已生成。" if facts["kind"]=="weekly_ready" else f"今日学习完成{facts['completed']}/{facts['tasks']}项，专注{facts['focus_minutes']}分钟。"
        return (prefix+advice)[:80]

    async def deliver(self,adapter,now):
        settings=await asyncio.to_thread(self.settings)
        facts=await asyncio.to_thread(self.facts,now)
        if facts is None:
            return False
        day=facts["date"]
        with self.study.repository._connect() as db:
            row=db.execute("SELECT * FROM study_supervision_deliveries WHERE local_date=?",(day,)).fetchone()
        if row and row["status"]=="delivered":
            return False
        if row and json.loads(row["facts_json"])!=facts:
            with self.study.repository._connect() as db:
                db.execute("DELETE FROM study_supervision_deliveries WHERE local_date=? AND status='pending'",(day,))
            return False
        if row is None:
            message=await asyncio.to_thread(self.message,facts)
            delivery_id="study:"+hashlib.sha256(str(self.study.repository.db_path).encode()).hexdigest()[:16]+":"+day
            with self.study.repository._connect() as db:
                db.execute("INSERT OR IGNORE INTO study_supervision_deliveries VALUES (?,?,?,?,?,?)",
                           (day,delivery_id,message,json.dumps(facts), "pending",now.isoformat()))
                row=db.execute("SELECT * FROM study_supervision_deliveries WHERE local_date=?",(day,)).fetchone()
        # Recheck consent, quiet hours and running timers after a slow model call.
        latest=await asyncio.to_thread(self.facts,self.study._now())
        if latest!=facts:
            with self.study.repository._connect() as db:
                db.execute("DELETE FROM study_supervision_deliveries WHERE local_date=? AND status='pending'",(day,))
            return False
        current=await asyncio.to_thread(self.settings)
        if not current.enabled or current.session_id!=settings.session_id:
            return False
        result=await adapter.send(current.session_id,row["message"],metadata={"delivery_id":row["delivery_id"]})
        if not result.success:
            return False
        with self.study.repository._connect() as db:
            db.execute("UPDATE study_supervision_deliveries SET status='delivered' WHERE local_date=?",(day,))
        return True


async def run_study_maintenance(runner,now):
    from honeyos.core.constants import get_honeyos_home
    from honeyos.gateway.config import Platform
    from honeyos.companion.work_mode import active_work
    if not (get_honeyos_home()/"study/study.db").exists():
        return
    try:
        store=await asyncio.to_thread(lambda:StudySupervision(StudyService()))
        await asyncio.to_thread(store.memory.maintain)
        adapter=runner.adapters.get(Platform.API_SERVER)
        if adapter is None or await asyncio.to_thread(active_work):
            return
        if getattr(adapter,"_companion_stream_controls",None) or runner._running_agents:
            return
        await store.deliver(adapter,now)
    except Exception:
        logger.exception("Study maintenance will retry on the next existing scheduler tick")
