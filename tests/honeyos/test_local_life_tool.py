from __future__ import annotations

import csv
import io
import json
import urllib.request

from honeyos.tools.local_life_tool import search_google_places, search_local_life
from honeyos.tools.tool_search import is_deferrable_tool_name


FIELDS = [
    "店名",
    "地址",
    "价格区间",
    "Google评分",
    "Google评论数",
    "营业时间",
    "walk-in政策",
    "推荐标签",
    "差评模式",
    "预约链接",
    "官网",
    "Yelp链接",
    "性别定位",
    "擅长风格(带置信度)",
]


def test_local_life_tools_are_never_deferred():
    assert is_deferrable_tool_name("google_maps_search") is False
    assert is_deferrable_tool_name("local_life_search") is False


def _write_index(tmp_path):
    root = tmp_path / "data" / "local-life"
    root.mkdir(parents=True)
    path = root / "salons.csv"
    rows = [
        {
            "店名": "Fast Barber",
            "地址": "1 Main St",
            "价格区间": "$45 cash only",
            "Google评分": "4.1",
            "Google评论数": "150",
            "营业时间": "Daily 9-5",
            "walk-in政策": "Walk-ins only, no appointment",
            "推荐标签": "经典男士快剪 免预约",
            "差评模式": "Saturday waits",
            "预约链接": "",
            "官网": "",
            "Yelp链接": "https://example.com/barber",
            "性别定位": "Men-only",
            "擅长风格(带置信度)": "Classic men's business cuts",
        },
        {
            "店名": "Color Studio",
            "地址": "9 Color Rd",
            "价格区间": "premium",
            "Google评分": "4.7",
            "Google评论数": "80",
            "营业时间": "Tue-Sat",
            "walk-in政策": "appointments recommended",
            "推荐标签": "Balayage专家 卷发友好",
            "差评模式": "expensive",
            "预约链接": "https://example.com/book",
            "官网": "https://example.com",
            "Yelp链接": "https://example.com/yelp",
            "性别定位": "unisex",
            "擅长风格(带置信度)": "balayage blonding curly hair",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    path.with_suffix(".meta.json").write_text(
        json.dumps(
            {
                "category": "hair_salon",
                "default_near": "Demo Station",
                "default_origin": {"lat": 37.0, "lon": -122.0},
                "locations": {
                    "Fast Barber": {"lat": 37.001, "lon": -122.0},
                    "Color Studio": {"lat": 37.03, "lon": -122.0},
                },
            }
        ),
        encoding="utf-8",
    )


def test_local_search_prefers_walk_in_barber_for_immediate_cut(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    _write_index(tmp_path)

    result = search_local_life(
        query="我现在想做一个男士普通快剪，最好不用预约",
        category="hair_salon",
        limit=2,
        home=tmp_path,
    )

    assert result["success"] is True
    assert result["fallback_required"] is False
    assert result["near"] == "Demo Station"
    assert result["results"][0]["name"] == "Fast Barber"
    assert result["results"][0]["distance_km"] is not None
    assert result["results"][0]["maps_url"].startswith("https://www.google.com/maps/")


def test_local_search_prefers_color_specialist_for_balayage(tmp_path):
    _write_index(tmp_path)

    result = search_local_life(
        query="我想染金发，做 balayage，也要适合卷发",
        category="hair_salon",
        limit=1,
        home=tmp_path,
    )

    assert result["results"][0]["name"] == "Color Studio"
    assert result["results"][0]["booking_url"] == "https://example.com/book"


def test_local_search_understands_short_chinese_hair_terms_without_category(tmp_path):
    _write_index(tmp_path)

    result = search_local_life(
        query="我想染一下卷发",
        limit=1,
        home=tmp_path,
    )

    assert result["results"][0]["name"] == "Color Studio"


def test_local_search_requests_fallback_when_category_is_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    _write_index(tmp_path)

    result = search_local_life(
        query="附近有没有修自行车的",
        category="bicycle_repair",
        home=tmp_path,
    )

    assert result["results"] == []
    assert result["fallback_required"] is True
    assert "maps" in result["fallback_hint"]


def test_missing_local_category_uses_google_places_when_configured(tmp_path, monkeypatch):
    _write_index(tmp_path)
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "secret-test-key")
    payload = {
        "places": [
            {
                "id": "place-1",
                "displayName": {"text": "Demo Bike Shop"},
                "formattedAddress": "20 Bike Ave",
                "rating": 4.8,
                "userRatingCount": 91,
                "googleMapsUri": "https://maps.google.com/example",
            }
        ]
    }

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    def _fake_urlopen(request, timeout):
        assert timeout == 12
        assert request.headers["X-goog-api-key"] == "secret-test-key"
        assert "secret-test-key" not in request.full_url
        return _Response(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    result = search_local_life(
        query="附近有没有修自行车的",
        category="bicycle_repair",
        home=tmp_path,
    )

    assert result["fallback_required"] is False
    assert result["live_lookup_used"] is True
    assert result["results"][0]["name"] == "Demo Bike Shop"


def test_google_maps_search_is_a_direct_native_api_call(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "secret-test-key")
    payload = {
        "places": [
            {
                "id": "restaurant-1",
                "displayName": {"text": "Nearby Noodles"},
                "formattedAddress": "1 University Ave, Palo Alto, CA",
                "rating": 4.7,
                "userRatingCount": 321,
                "googleMapsUri": "https://maps.google.com/noodles",
                "location": {"latitude": 37.421, "longitude": -122.139},
            }
        ]
    }

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    def _fake_urlopen(request, timeout):
        assert timeout == 12
        assert request.method == "POST"
        assert request.full_url == "https://places.googleapis.com/v1/places:searchText"
        assert request.headers["X-goog-api-key"] == "secret-test-key"
        assert "secret-test-key" not in request.full_url
        body = json.loads(request.data.decode())
        if body["textQuery"] == "Tencent Palo Alto Office":
            return _Response(
                b'{"places":[{"location":{"latitude":37.42,"longitude":-122.14}}]}'
            )
        assert body["textQuery"] == "评分 4.5 以上的中餐 near Tencent Palo Alto Office"
        assert "includedType" not in body
        return _Response(json.dumps(payload).encode())

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    result = search_google_places(
        query="评分 4.5 以上的中餐",
        near="Tencent Palo Alto Office",
        limit=3,
    )

    assert result["success"] is True
    assert result["provider"] == "google_places_api"
    assert result["fallback_required"] is False
    assert result["results"][0]["name"] == "Nearby Noodles"
    assert result["results"][0]["distance_km"] is not None


def test_google_maps_search_restricts_hair_queries_to_salons(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "secret-test-key")
    captured = {}

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    def _fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode()))
        return _Response(b'{"places": []}')

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    search_google_places(
        query="高分理发店，适合染金发",
        near="Tencent Palo Alto Office",
        limit=3,
    )

    assert captured["includedType"] == "hair_salon"


def test_google_places_search_requires_location(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "secret-test-key")

    result = search_google_places(query="理发店", near="")

    assert result["success"] is False
    assert result["fallback_required"] is False
    assert result["error"] == "near is required"


def test_google_maps_reports_when_photo_fallback_is_needed(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "secret-test-key")

    class _Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: _Response(
            b'{"places":[{"id":"p1","displayName":{"text":"No Photo Cafe"}}]}'
        ),
    )

    result = search_google_places(query="cafe", near="Stanford", limit=1)

    assert result["success"] is True
    assert result["photo_fallback_required"] is True
