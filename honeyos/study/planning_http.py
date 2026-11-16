"""Study planning actions that require an authenticated browser request."""

import asyncio

from aiohttp import web

from .markdown import export_study_plan_markdown
from .planning import preview_chat_plan, save_chat_plan, template_markdown
from .reminders import change_reminder, list_reminders
from .service import StudyService


def planning_routes(adapter):
    async def template(_request):
        return web.Response(text=template_markdown(), content_type="text/markdown",
                            headers={"Content-Disposition": "attachment; filename=study-plan-template.md"})

    async def export(request):
        try:
            plan = await asyncio.to_thread(StudyService().get_plan, request.match_info["plan_id"])
        except KeyError:
            return web.json_response({"error": "找不到学习计划。"}, status=404)
        return web.Response(text=export_study_plan_markdown(plan), content_type="text/markdown",
                            headers={"Content-Disposition": "attachment; filename=study-plan.md"})

    async def run(request, *, save):
        body, error = await adapter._read_json_body(request)
        if error is not None:
            return error
        markdown = body.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip() or len(markdown) > 100_000:
            return web.json_response({"error": "计划正文无效。"}, status=400)
        revision = body.get("revision") is True
        try:
            if save:
                plan = await asyncio.to_thread(save_chat_plan, StudyService(), markdown, revision=revision,
                                               expected_updated_at=body.get("expected_updated_at"),
                                               plan_id=body.get("plan_id"))
                return web.json_response({"plan": plan.model_dump(mode="json")})
            plan, original = await asyncio.to_thread(preview_chat_plan, StudyService(), markdown, revision=revision)
            return web.json_response({
                "plan": plan.model_dump(mode="json"),
                "expected_updated_at": original.updated_at.isoformat() if original else None,
            })
        except KeyError:
            return web.json_response({"error": "要更新的学习计划已不存在。"}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def preview(request):
        return await run(request, save=False)

    async def save(request):
        return await run(request, save=True)

    async def reminders(request):
        try:
            values = await asyncio.to_thread(list_reminders, StudyService(), request.match_info["plan_id"])
        except KeyError:
            return web.json_response({"error": "找不到学习计划。"}, status=404)
        return web.json_response({"reminders": values})

    async def set_reminder(request):
        body, error = await adapter._read_json_body(request)
        if error is not None:
            return error
        if "time" not in body:
            return web.json_response({"error": "缺少提醒时刻。"}, status=400)
        session_id = ""
        if body["time"] is not None:
            session_id = body.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                return web.json_response({"error": "请先打开 HoneyOS 聊天，再设置提醒。"}, status=400)
            _, error = await adapter._get_existing_session_or_404(session_id)
            if error is not None:
                return error
        try:
            await asyncio.to_thread(change_reminder, StudyService(), request.match_info["plan_id"],
                                    request.match_info["task_id"], body["time"], session_id)
        except KeyError:
            return web.json_response({"error": "找不到学习计划或任务。"}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"time": body["time"]})

    routes = [
        ("GET", "/api/study/plans/template", template),
        ("GET", "/api/study/plans/{plan_id}/markdown", export),
        ("POST", "/api/study/chat-plans/preview", preview),
        ("POST", "/api/study/chat-plans/confirm", save),
        ("GET", "/api/study/plans/{plan_id}/reminders", reminders),
        ("PUT", "/api/study/plans/{plan_id}/tasks/{task_id}/reminder", set_reminder),
    ]
    return [(method, path, adapter._authenticated_file_handler(handler)) for method, path, handler in routes]
