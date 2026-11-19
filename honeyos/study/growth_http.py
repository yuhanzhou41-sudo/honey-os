"""Authenticated Study growth, memory and event ownership actions."""
import asyncio
import json
import logging
import sqlite3
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from aiohttp import web

from .service import StudyService
from .growth import StudyGrowth
from .learning import StudyLearningMemory
from .activity import assign_event


logger=logging.getLogger(__name__)

def growth_routes(adapter):
    async def supervision(request):
        from .supervision import StudySupervision
        store=await asyncio.to_thread(lambda:StudySupervision(StudyService()))
        if request.method=="GET":
            return web.json_response((await asyncio.to_thread(store.settings)).model_dump())
        body,error=await adapter._read_json_body(request)
        if error is not None:
            return error
        if body.get("enabled") is True:
            _,error=await adapter._get_existing_session_or_404(body.get("session_id",""))
            if error is not None:
                return error
        try:
            return web.json_response(await asyncio.to_thread(store.configure,body))
        except (ValueError,TypeError,ZoneInfoNotFoundError) as exc:
            return web.json_response({"error":str(exc)},status=400)

    async def handle(request,action):
        body={}
        if request.method!="GET":
            body,error=await adapter._read_json_body(request)
            if error is not None:
                return error
        def run():
            study=StudyService()
            growth=StudyGrowth(study)
            memory=StudyLearningMemory(study)
            plan_id=request.match_info.get("plan_id")
            if plan_id:
                study.get_plan(plan_id)
                setting=growth.settings(plan_id)
                zone=ZoneInfo(json.loads(setting["settings_json"])["timezone"] if setting else "Asia/Shanghai")
            else:
                from honeyos.core.time import local_timezone
                zone=local_timezone()
            local_today=study._now().astimezone(zone).date().isoformat()
            if action=="enable":
                return growth.enable(plan_id,body)
            if action=="state":
                return growth.state(plan_id)
            if action=="ledger":
                with study.repository._connect() as db:
                    return {"entries":[dict(row) for row in db.execute(
                        "SELECT id,source,amount,created_at FROM study_reward_ledger WHERE plan_id=? ORDER BY id DESC LIMIT 200",(plan_id,))]}
            if action=="memory":
                day=request.query.get("date",local_today)
                return memory.snapshot(plan_id,day)
            if action=="weekly":
                return memory.weekly(plan_id,request.query.get("date",local_today))
            if action=="recovery":
                return growth.recovery(plan_id,body.get("date",""))
            if action=="flex-preview":
                original,proposed=growth.flex_preview(plan_id,body.get("task_id"),body.get("slot_id"))
                return {"plan":proposed.model_dump(mode="json"),
                        "expected_updated_at":original.updated_at.isoformat(),"capacity":study.plan_capacity(proposed)}
            if action=="flex-confirm":
                if not body.get("expected_updated_at"):
                    raise ValueError("请先预览机动调整。")
                saved=growth.use_flex(plan_id,body.get("task_id"),body.get("slot_id"),
                                      body.get("request_id"),body.get("expected_updated_at"))
                return {"plan":saved.model_dump(mode="json")}
            if action=="flex-undo":
                if not body.get("expected_updated_at"):
                    raise ValueError("请先核对当前计划。")
                saved=growth.undo_flex(plan_id,body.get("request_id"),body["expected_updated_at"])
                return {"plan":saved.model_dump(mode="json")}
            if action=="close-preview":
                return memory.close_preview(plan_id,body.get("reason"))
            if action=="close-confirm":
                if not body.get("expected_updated_at") or not body.get("facts_revision"):
                    raise ValueError("请先预览结束归档。")
                return memory.close(plan_id,body.get("reason"),body["expected_updated_at"],body["facts_revision"])
            if action=="assign":
                assign_event(study,body.get("kind"),body.get("event_id"),body.get("plan_id"))
                # Rebuild balances for every enabled plan to reverse an old owner immediately.
                with study.repository._connect() as db:
                    plans=[row[0] for row in db.execute("SELECT plan_id FROM study_growth_settings")]
                for owner in plans:
                    growth.state(owner)
                return {"saved":True}
            if action=="events":
                with study.repository._connect() as db:
                    events=[]
                    for kind,table in (("attempt","study_learning_attempts"),("recall","study_learning_recalls")):
                        source_table="study_review_questions" if kind=="attempt" else "study_review_cards"
                        source_key="question_id" if kind=="attempt" else "card_id"
                        source_text="prompt" if kind=="attempt" else "front"
                        events.extend({"kind":kind,**dict(row)} for row in db.execute(
                            f"SELECT e.id,e.created_at,a.plan_id,COALESCE(q.{source_text},"
                            "json_extract(arc.payload_json,'$.source.source_title'),'已归档学习事件') AS summary "
                            f"FROM {table} e LEFT JOIN {source_table} q ON q.id=e.{source_key} "
                            "LEFT JOIN study_activity_attribution a ON a.event_id=e.id AND a.kind=? "
                            "LEFT JOIN study_activity_archive arc ON arc.event_id=e.id AND arc.kind=a.kind "
                            "ORDER BY e.created_at DESC LIMIT 100",(kind,)))
                return {"events":events}
            if action=="overview":
                day=request.query.get("date",local_today)
                snapshots=[]
                for plan in study.list_plans():
                    setting=growth.settings(plan.id)
                    zone=json.loads(setting["settings_json"])["timezone"] if setting else "Asia/Shanghai"
                    snapshots.append(growth.facts(plan.id,day,zone))
                return {"date":day,"plans":snapshots,
                        "focus_minutes":round(sum(item["focus_minutes"] for item in snapshots),2)}
            raise ValueError("不支持的学习操作。")
        try:
            result=await asyncio.to_thread(run)
            return web.json_response(result)
        except sqlite3.Error:
            logger.exception("Study growth transaction failed")
            return web.json_response({"error":"学习记录暂时无法保存，请稍后重试。"},status=503)
        except KeyError:
            return web.json_response({"error":"计划、任务或学习事件不存在。"},status=404)
        except (ValueError,TypeError,ZoneInfoNotFoundError) as exc:
            return web.json_response({"error":str(exc)},status=400)
    actions={
        "state":"GET","ledger":"GET","enable":"POST","memory":"GET","weekly":"GET","recovery":"POST",
        "flex-preview":"POST","flex-confirm":"POST","flex-undo":"POST",
        "close-preview":"POST","close-confirm":"POST",
    }
    routes=[
        ("GET","/api/study/growth/supervision",adapter._authenticated_file_handler(supervision)),
        ("PUT","/api/study/growth/supervision",adapter._authenticated_file_handler(supervision)),
    ]
    for action,method in actions.items():
        async def scoped(request, name=action):
            return await handle(request,name)
        routes.append((method,f"/api/study/plans/{{plan_id}}/growth/{action}",adapter._authenticated_file_handler(scoped)))
    for action,method in {"assign":"POST","events":"GET","overview":"GET"}.items():
        async def global_action(request,name=action):
            return await handle(request,name)
        routes.append((method,f"/api/study/growth/{action}",adapter._authenticated_file_handler(global_action)))
    return routes
