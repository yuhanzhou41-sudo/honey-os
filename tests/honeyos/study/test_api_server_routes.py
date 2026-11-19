from honeyos.gateway.config import PlatformConfig
from honeyos.gateway.platforms.api_server import APIServerAdapter


def _adapter():
    return APIServerAdapter(
        PlatformConfig(
            enabled=True,
            extra={"host": "127.0.0.1", "port": 8642, "key": "a" * 32},
        )
    )


def test_phase2_study_routes_registered_exactly_once():
    pairs = [(method, path) for method, path, _ in _adapter()._http_route_table()]
    expected = [
        ("GET", "/api/study/plans"),
        ("POST", "/api/study/plans"),
        ("GET", "/api/study/plans/{plan_id}"),
        ("PATCH", "/api/study/plans/{plan_id}"),
        ("DELETE", "/api/study/plans/{plan_id}"),
        ("POST", "/api/study/plans/{plan_id}/tasks"),
        ("PATCH", "/api/study/plans/{plan_id}/tasks/{task_id}"),
        ("DELETE", "/api/study/plans/{plan_id}/tasks/{task_id}"),
        ("POST", "/api/study/plans/{plan_id}/tasks/{task_id}/status"),
    ]
    for route in expected:
        assert pairs.count(route) == 1


def test_retired_legacy_companion_study_route_stays_absent():
    pairs = [(method, path) for method, path, _ in _adapter()._http_route_table()]
    assert pairs.count(("GET", "/api/companion/study")) == 0
    assert pairs.count(("GET", "/study")) == 1
