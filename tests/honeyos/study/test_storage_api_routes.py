from pathlib import Path

def test_storage_routes_once():
    s=Path('honeyos/gateway/platforms/api_server.py').read_text(encoding='utf-8')
    for route in [
        '("GET", "/api/study/storage/libraries"',
        '("POST", "/api/study/storage/libraries"',
        '("POST", "/api/study/storage/discover"',
        '("POST", "/api/study/storage/libraries/{library_id}/cleanup"',
    ]: assert s.count(route)==1
