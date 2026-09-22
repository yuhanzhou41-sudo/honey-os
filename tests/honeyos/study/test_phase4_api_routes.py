from pathlib import Path


def test_phase4_study_library_routes_present():
    source=Path('honeyos/gateway/platforms/api_server.py').read_text(encoding='utf-8')
    expected=[
        '("GET", "/api/study/resources"', '("POST", "/api/study/resources"',
        '("GET", "/api/study/resources/search"', '("GET", "/api/study/resources/{resource_id}"',
        '("PATCH", "/api/study/resources/{resource_id}"', '("DELETE", "/api/study/resources/{resource_id}"',
        '("GET", "/api/study/resources/{resource_id}/content"',
    ]
    for route in expected: assert source.count(route) == 1
