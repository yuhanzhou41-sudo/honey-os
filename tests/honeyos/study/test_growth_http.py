import asyncio
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

from aiohttp import web
from aiohttp.test_utils import TestClient,TestServer
from honeyos.gateway.config import PlatformConfig
from honeyos.gateway.platforms.api_server import APIServerAdapter
from honeyos.study.growth_http import growth_routes
from honeyos.study.models import StudyPlan
from honeyos.study.repository import StudyRepository
from honeyos.study.service import StudyService


def test_growth_flex_memory_weekly_close_real_http(tmp_path,monkeypatch):
    monkeypatch.setenv("HONEYOS_HOME",str(tmp_path))
    study=StudyService(StudyRepository(tmp_path))
    today=datetime.now(ZoneInfo("Asia/Shanghai")).date()
    tomorrow=today+timedelta(days=1)
    def new_plan():
        return study.repository.save_new_plan(StudyPlan(
            schema_version=2,title="HTTP",status="active",start_date=today,end_date=today+timedelta(days=7),
            tasks=[{"title":"Essential","scheduled_date":today,"priority":"must","minimum_required":True,"planned_minutes":15}],
            flex_slots=[{"scheduled_date":tomorrow,"planned_minutes":30}],
        ))
    first,second=new_plan(),new_plan()
    adapter=APIServerAdapter(PlatformConfig(enabled=True,extra={"host":"127.0.0.1","port":8642,"key":"a"*32}))
    root=f"/api/study/plans/{first.id}/growth/"
    async def scenario():
        app=web.Application()
        for method,path,handler in growth_routes(adapter):
            app.router.add_route(method,path,handler)
        async with TestClient(TestServer(app)) as client:
            assert (await client.get(root+"state")).status==401
            headers={"Authorization":"Bearer "+"a"*32}
            response=await client.post(root+"enable",json={"timezone":"Asia/Shanghai","minimum_mode":True},headers=headers)
            assert response.status==200, await response.text()
            assert (await response.json())["enabled"]
            payload={"task_id":first.tasks[0].id,"slot_id":first.flex_slots[0].id}
            response=await client.post(root+"flex-preview",json=payload,headers=headers)
            assert response.status==200, await response.text()
            preview=await response.json()
            assert study.get_plan(first.id).tasks[0].scheduled_date==today
            confirm={**payload,"request_id":"http-operation","expected_updated_at":preview["expected_updated_at"]}
            response=await client.post(root+"flex-confirm",json=confirm,headers=headers)
            assert response.status==200, await response.text()
            saved=(await response.json())["plan"]
            assert saved["tasks"][0]["scheduled_date"]==tomorrow.isoformat()
            assert (await client.post(root+"flex-confirm",json=confirm,headers=headers)).status==200
            response=await client.post(root+"flex-undo",json={"request_id":"http-operation","expected_updated_at":saved["updated_at"]},headers=headers)
            assert response.status==200, await response.text()
            response=await client.get(root+"memory?date="+today.isoformat(),headers=headers)
            assert response.status==200 and (await response.json())["tasks"]==1
            response=await client.get(root+"weekly?date="+today.isoformat(),headers=headers)
            assert response.status==200, await response.text()
            response=await client.post(root+"close-preview",json={"reason":"stopped"},headers=headers)
            proposal=await response.json()
            assert "summary" in proposal
            response=await client.post(root+"close-confirm",json=proposal,headers=headers)
            assert response.status==200, await response.text()
            assert (await response.json())["reason"]=="stopped"
            response=await client.get(root+"weekly?date="+today.isoformat(),headers=headers)
            assert (await response.json())["archived"]
            assert study.get_plan(second.id).status.value=="active"
            response=await client.get(root+"state",headers=headers)
            assert (await response.json())["final_summary"]
    asyncio.run(scenario())
