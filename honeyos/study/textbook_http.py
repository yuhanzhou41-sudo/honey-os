"""Authenticated Study textbook routes (index / locate / collect / cleanup)."""

from __future__ import annotations

import asyncio
import logging

from aiohttp import web

from .textbook import TextbookService

logger = logging.getLogger(__name__)
MAX_DUMP = 4 * 1024 * 1024


def textbook_routes(adapter):
    def route(action, *, post=False, loopback=False, status=200):
        async def handle(request):
            if loopback and not adapter._request_is_loopback(request):
                return web.json_response({"error": "请从本机 Study 页面使用此功能。"}, status=403)
            body = {}
            if post:
                body, error = await adapter._read_json_body(request)
                if error is not None:
                    return error
            try:
                result = await asyncio.to_thread(action, body, request)
            except KeyError:
                return web.json_response({"error": "找不到对应的教材或章节。"}, status=404)
            except ValueError as exc:
                return web.json_response({"error": str(exc)}, status=400)
            except Exception:
                logger.warning("Study textbook request failed", exc_info=True)
                return web.json_response({"error": "教材采集暂时不可用，请稍后重试。"}, status=502)
            return web.json_response(result, status=status)

        return adapter._authenticated_file_handler(handle)

    def service() -> TextbookService:
        return TextbookService()

    def index_book(body, _request):
        dump = body.get("dump")
        text = body.get("text")
        book_id = str(body.get("book_id") or "").strip()
        if not book_id:
            raise ValueError("请填写教材编号。")
        title = str(body.get("title") or "").strip()
        if body.get("from_device") is True:
            outline = service().sync_outline_from_device(book_id, title=title)
        elif isinstance(dump, str) and dump.strip():
            if len(dump) > MAX_DUMP:
                raise ValueError("UI dump 过大。")
            outline = service().sync_outline_from_dump(
                book_id, dump, title=title, package=str(body.get("package") or "")
            )
        elif isinstance(text, str) and text.strip():
            outline = service().sync_outline_from_text(book_id, text, title=title)
        else:
            raise ValueError("请提供 UI dump 或目录文本。")
        return {
            "book_id": outline.book_id,
            "title": outline.title,
            "sections": [item.to_dict() for item in outline.sections],
        }

    def locate(body, _request):
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("请说明要查的教材内容。")
        book_id = body.get("book_id") or None
        limit = body.get("limit", 3)
        return {"hits": service().locate(query, book_id=book_id, limit=int(limit))}

    def collect(body, _request):
        book_id = str(body.get("book_id") or "").strip()
        section_id = str(body.get("section_id") or "").strip()
        title = str(body.get("section_title") or "").strip()
        if not book_id or not (section_id or title):
            raise ValueError("请指定教材与章节。")
        service_instance = service()
        force = body.get("force") is True
        if section_id:
            payload = service_instance.collect_section(book_id, section_id, force=force)
        else:
            payload = service_instance.collect_by_title(
                book_id, title, chapter=str(body.get("chapter") or ""), force=force
            )
        text = payload.pop("text", "")
        payload["preview"] = text[:400]
        return payload

    def cleanup(body, _request):
        if body.get("purge_temp") is True:
            return {"temp": service().purge_temp()}
        max_bytes = body.get("max_bytes")
        ttl_days = body.get("ttl_days")
        return service().cleanup(
            max_bytes=int(max_bytes) if isinstance(max_bytes, int) else None,
            ttl_days=float(ttl_days) if isinstance(ttl_days, (int, float)) else None,
        )

    def release(body, _request):
        book_id = str(body.get("book_id") or "").strip()
        section_ids = body.get("section_ids")
        if not book_id or not isinstance(section_ids, list) or not section_ids:
            raise ValueError("请指定要释放的教材章节。")
        return service().release_after_review(book_id, [str(item) for item in section_ids])

    root = "/api/study/textbook"
    return [
        ("GET", root + "/books", route(lambda b, r: {"books": service().list_books()})),
        ("POST", root + "/index", route(index_book, post=True)),
        ("POST", root + "/locate", route(locate, post=True)),
        ("POST", root + "/collect", route(collect, post=True, loopback=True)),
        ("GET", root + "/stats", route(lambda b, r: service().stats())),
        ("POST", root + "/cleanup", route(cleanup, post=True)),
        ("POST", root + "/release", route(release, post=True)),
    ]
