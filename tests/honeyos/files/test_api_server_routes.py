from honeyos.gateway.config import PlatformConfig
from honeyos.gateway.platforms.api_server import APIServerAdapter


def _adapter() -> APIServerAdapter:
    return APIServerAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "host": "127.0.0.1",
                "port": 8642,
                "key": "a" * 32,
            },
        )
    )


def test_attachment_routes_are_registered_exactly_once():
    routes = _adapter()._http_route_table()
    pairs = [(method, path) for method, path, _handler in routes]

    expected = [
        ("POST", "/api/attachments"),
        ("GET", "/api/attachments"),
        ("GET", "/api/attachments/{attachment_id}"),
        ("GET", "/api/attachments/{attachment_id}/content"),
        ("DELETE", "/api/attachments/{attachment_id}"),
        ("POST", "/api/attachments/{attachment_id}/restore"),
    ]

    for route in expected:
        assert pairs.count(route) == 1


def test_attachment_routes_do_not_replace_existing_namespaces():
    routes = _adapter()._http_route_table()
    pairs = [(method, path) for method, path, _handler in routes]

    preserved = [
        ("GET", "/api/companion/memories"),
        ("GET", "/api/study/plans"),
        ("GET", "/api/companion/diary"),
        ("GET", "/api/sessions"),
        ("POST", "/api/sessions"),
    ]

    for route in preserved:
        assert pairs.count(route) == 1


def test_attachment_routes_use_generic_attachment_namespace():
    routes = _adapter()._http_route_table()

    attachment_paths = {
        path
        for _method, path, _handler in routes
        if path.startswith("/api/attachments")
    }

    assert attachment_paths
    assert all(
        not path.startswith("/api/companion/memories")
        and not path.startswith("/api/companion/study")
        for path in attachment_paths
    )
