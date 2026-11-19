"""Study planning actions that require an authenticated browser request."""

import asyncio

from aiohttp import web

from .markdown import export_study_plan_markdown
from .planning import (
    authoring_guide, build_planning_request, planning_capabilities,
    preview_chat_plan, save_chat_plan, template_markdown,
)
from .reminders import change_reminder, list_reminders
from .service import StudyService


def planning_routes(adapter):
    async def capabilities(_request):
        return web.json_response(planning_capabilities())

    async def template(request):
        try:
            value = request.query.get("version")
            version = int(value) if value is not None else None
            raw = template_markdown(version)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.Response(text=raw, content_type="text/markdown",
                            headers={"Content-Disposition": "attachment; filename=study-plan-template.md"})

    async def guide(_request):
        return web.Response(text="# StudyPlan Authoring Guide\n\n" + authoring_guide() + "\n",
                            content_type="text/markdown",
                            headers={"Content-Disposition": "attachment; filename=AI_AUTHORING_GUIDE.md"})

    async def planning_request(request):
        body, error = await adapter._read_json_body(request)
        if error is not None:
            return error
        try:
            markdown = await asyncio.to_thread(build_planning_request, StudyService(), body)
        except KeyError:
            return web.json_response({"error": "所选计划或资料不存在。"}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.Response(text=markdown, content_type="text/markdown",
                            headers={"Content-Disposition": "attachment; filename=planning_request.md"})

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
                "capacity": await asyncio.to_thread(StudyService().plan_capacity, plan),
            })
        except KeyError:
            return web.json_response({"error": "要更新的学习计划已不存在。"}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def preview(request):
        return await run(request, save=False)

    async def save(request):
        return await run(request, save=True)

    async def capacity(request):
        try:
            study = StudyService()
            plan = await asyncio.to_thread(study.get_plan, request.query.get("plan_id", ""))
            return web.json_response({"capacity": await asyncio.to_thread(study.plan_capacity, plan)})
        except KeyError:
            return web.json_response({"error": "找不到学习计划。"}, status=404)

    async def set_capacity(request):
        body, error = await adapter._read_json_body(request)
        if error is not None:
            return error
        if "minutes" not in body:
            return web.json_response({"error": "缺少每日学习上限。"}, status=400)
        try:
            await asyncio.to_thread(
                StudyService().set_daily_capacity,
                request.match_info["local_date"], body["minutes"],
            )
        except (ValueError, TypeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response({"saved": True})

    async def change(request):
        body, error = await adapter._read_json_body(request)
        if error is not None:
            return error
        try:
            study = StudyService()
            if request.path.endswith("/confirm"):
                expected = body.get("expected_updated_at")
                if not isinstance(expected, str) or not expected:
                    raise ValueError("请先预览本次修改。")
                plan = await asyncio.to_thread(
                    study.confirm_update, request.match_info["plan_id"], body.get("patch"),
                    task_id=body.get("task_id"), expected_updated_at=expected,
                )
                return web.json_response({"plan": plan.model_dump(mode="json")})
            original, plan = await asyncio.to_thread(
                study.preview_update, request.match_info["plan_id"],
                body.get("patch"), task_id=body.get("task_id"),
            )
            return web.json_response({
                "plan": plan.model_dump(mode="json"),
                "expected_updated_at": original.updated_at.isoformat(),
                "capacity": await asyncio.to_thread(study.plan_capacity, plan),
            })
        except KeyError:
            return web.json_response({"error": "计划或任务不存在。"}, status=404)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

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
        ("POST", "/api/study/plans/{plan_id}/changes/preview", change),
        ("POST", "/api/study/plans/{plan_id}/changes/confirm", change),
        ("GET", "/api/study/planning/capabilities", capabilities),
        ("GET", "/api/study/planning/guide", guide),
        ("POST", "/api/study/planning/request", planning_request),
        ("GET", "/api/study/capacity", capacity),
        ("PUT", "/api/study/capacity/{local_date}", set_capacity),
        ("GET", "/api/study/plans/template", template),
        ("GET", "/api/study/plans/{plan_id}/markdown", export),
        ("POST", "/api/study/chat-plans/preview", preview),
        ("POST", "/api/study/chat-plans/confirm", save),
        ("GET", "/api/study/plans/{plan_id}/reminders", reminders),
        ("PUT", "/api/study/plans/{plan_id}/tasks/{task_id}/reminder", set_reminder),
    ]
    return [(method, path, adapter._authenticated_file_handler(handler)) for method, path, handler in routes]
