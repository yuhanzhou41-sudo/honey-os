import asyncio

from aiohttp.test_utils import TestClient, TestServer
from aiohttp import web

from honeyos.files.http import AttachmentHTTPHandlers
from honeyos.gateway.config import PlatformConfig
from honeyos.gateway.platforms.api_server import APIServerAdapter


async def make_client(tmp_path):
    handlers = AttachmentHTTPHandlers(
        tmp_path / "attachments",
        max_attachment_bytes=1024,
    )

    app = web.Application()

    app.router.add_post("/api/attachments", handlers.upload)
    app.router.add_get("/api/attachments", handlers.list)
    app.router.add_get(
        "/api/attachments/{attachment_id}",
        handlers.get,
    )
    app.router.add_get(
        "/api/attachments/{attachment_id}/content",
        handlers.content,
    )
    app.router.add_delete(
        "/api/attachments/{attachment_id}",
        handlers.delete,
    )
    app.router.add_post(
        "/api/attachments/{attachment_id}/restore",
        handlers.restore,
    )

    server = TestServer(app)
    client = TestClient(server)

    await client.start_server()

    return client


def test_attachment_http_round_trip(tmp_path):
    async def scenario():
        client = await make_client(tmp_path)

        try:
            form = __import__("aiohttp").FormData()
            form.add_field(
                "file",
                b"hello honeyos",
                filename="notes.txt",
                content_type="text/plain",
            )

            response = await client.post(
                "/api/attachments",
                data=form,
            )

            assert response.status == 201

            payload = await response.json()
            attachment = payload["attachment"]

            attachment_id = attachment["id"]

            assert attachment["original_filename"] == "notes.txt"
            assert attachment["declared_mime_type"] == "text/plain"

            response = await client.get(
                f"/api/attachments/{attachment_id}"
            )

            assert response.status == 200

            response = await client.get(
                f"/api/attachments/{attachment_id}/content"
            )

            assert response.status == 200
            assert await response.read() == b"hello honeyos"

            response = await client.delete(
                f"/api/attachments/{attachment_id}"
            )

            assert response.status == 200

            deleted = (await response.json())["attachment"]
            assert deleted["status"] == "deleted"

            response = await client.get(
                f"/api/attachments/{attachment_id}/content"
            )

            assert response.status == 410

            response = await client.post(
                f"/api/attachments/{attachment_id}/restore"
            )

            assert response.status == 200

            response = await client.get(
                f"/api/attachments/{attachment_id}/content"
            )

            assert response.status == 200
            assert await response.read() == b"hello honeyos"

        finally:
            await client.close()

    asyncio.run(scenario())


def test_attachment_http_lists_uploads(tmp_path):
    async def scenario():
        client = await make_client(tmp_path)

        try:
            for name in ("one.txt", "two.txt"):
                form = __import__("aiohttp").FormData()
                form.add_field(
                    "file",
                    name.encode(),
                    filename=name,
                    content_type="text/plain",
                )

                response = await client.post(
                    "/api/attachments",
                    data=form,
                )

                assert response.status == 201

            response = await client.get("/api/attachments")

            assert response.status == 200

            payload = await response.json()

            assert len(payload["attachments"]) == 2

        finally:
            await client.close()

    asyncio.run(scenario())


def test_attachment_http_rejects_missing_file(tmp_path):
    async def scenario():
        client = await make_client(tmp_path)

        try:
            form = __import__("aiohttp").FormData()
            form.add_field("source_type", "upload")

            response = await client.post(
                "/api/attachments",
                data=form,
            )

            assert response.status in {400, 415}

        finally:
            await client.close()

    asyncio.run(scenario())


def test_attachment_http_rejects_oversize(tmp_path):
    async def scenario():
        client = await make_client(tmp_path)

        try:
            form = __import__("aiohttp").FormData()
            form.add_field(
                "file",
                b"x" * 2048,
                filename="large.bin",
                content_type="application/octet-stream",
            )

            response = await client.post(
                "/api/attachments",
                data=form,
            )

            assert response.status == 413

        finally:
            await client.close()

    asyncio.run(scenario())


def test_attachment_http_missing_id_returns_404(tmp_path):
    async def scenario():
        client = await make_client(tmp_path)

        try:
            response = await client.get(
                "/api/attachments/att_missing"
            )

            assert response.status == 404

        finally:
            await client.close()

    asyncio.run(scenario())


def test_gateway_attachment_routes_require_existing_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    key = "a" * 32
    adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": key}))
    app = web.Application()
    for method, path, handler in adapter._http_route_table():
        if path.startswith("/api/attachments"):
            app.router.add_route(method, path, handler)

    async def scenario():
        async with TestClient(TestServer(app)) as client:
            endpoints = (
                ("POST", "/api/attachments"),
                ("GET", "/api/attachments"),
                ("GET", "/api/attachments/missing"),
                ("GET", "/api/attachments/missing/content"),
                ("DELETE", "/api/attachments/missing"),
                ("POST", "/api/attachments/missing/restore"),
            )
            for method, path in endpoints:
                for headers in ({}, {"Authorization": "Bearer invalid"}):
                    async with client.request(method, path, headers=headers) as response:
                        assert response.status == 401, (method, path)
                        assert (await response.json())["error"]["code"] == "gateway_auth_failed"

            async with client.get(
                "/api/attachments", headers={"Authorization": f"Bearer {key}"}
            ) as response:
                assert response.status == 200
                assert await response.json() == {"attachments": []}

            async with client.get(
                "/api/attachments", cookies={"honeyos_local": adapter._local_web_token}
            ) as response:
                assert response.status == 200
                assert await response.json() == {"attachments": []}

    asyncio.run(scenario())
