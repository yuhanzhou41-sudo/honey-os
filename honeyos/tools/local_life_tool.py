"""Private, local-first discovery for nearby businesses and services."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import re
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import httpx

from honeyos.tools.registry import registry


logger = logging.getLogger(__name__)


def _httpx_json(
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict[str, Any] | None = None,
    timeout: float = 12,
) -> dict[str, Any]:
    """Network fallback for macOS urllib TLS/SNI failures."""
    if json_body is None:
        response = httpx.get(url, headers=headers, timeout=timeout, trust_env=False)
    else:
        response = httpx.post(
            url,
            headers=headers,
            json=json_body,
            timeout=timeout,
            trust_env=False,
        )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _httpx_bytes(url: str, *, headers: dict[str, str], timeout: float = 15) -> bytes:
    response = httpx.get(url, headers=headers, timeout=timeout, trust_env=False)
    response.raise_for_status()
    return response.content


LOCAL_LIFE_SEARCH_SCHEMA = {
    "name": "local_life_search",
    "description": (
        "Search the user's private on-device local-life indexes for nearby businesses "
        "and services. Use this before public map or web search when the user asks for "
        "a nearby shop, salon, restaurant, or other local recommendation. Results include "
        "fit signals, cautions, and clickable map/booking links. Do not mention the index "
        "format, file name, row count, or source implementation to the user. Do not call "
        "web_search unless this tool returns fallback_required=true. When image_path is "
        "present, include it once as MEDIA:<image_path> in the final response."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "What the user wants, including useful remembered preferences such as "
                    "budget, style, timing, or walk-in needs."
                ),
            },
            "category": {
                "type": "string",
                "description": "Optional normalized category, for example hair_salon.",
            },
            "near": {
                "type": "string",
                "description": (
                    "Current location, address, or landmark. Omit only when the local index "
                    "has a configured default area."
                ),
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["query"],
    },
}


GOOGLE_MAPS_SEARCH_SCHEMA = {
    "name": "google_maps_search",
    "description": (
        "Search Google Places API directly for current nearby businesses and points of "
        "interest. MUST use this tool—not web_search, terminal, or a maps skill—when the "
        "user asks for the nearest/nearby shop, restaurant, salon, attraction, rating, "
        "open-now status, business photo, or Google Maps link. This is a native tool: it "
        "does not require approval. Use public web/Yelp search only when this tool returns "
        "fallback_required=true. Put a returned maps_url on its own line in messaging "
        "responses; when image_path is present include MEDIA:<image_path> exactly once. "
        "Return rating, distance, a Maps link, and one photo by default. When "
        "photo_fallback_required=true, a Yelp web search is allowed only to add a "
        "Yelp rating/page whose rich preview can supply a visual card."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Business/category and constraints, e.g. a 4.5+ rated hair salon.",
            },
            "near": {
                "type": "string",
                "description": "The user's address, office, landmark, neighborhood, or city.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["query", "near"],
    },
}


_CATEGORY_SYNONYMS = {
    "hair_salon": (
        "理发",
        "剪发",
        "剪",
        "发型",
        "染发",
        "染",
        "卷发",
        "烫发",
        "hair",
        "haircut",
        "salon",
        "barber",
    ),
}


@lru_cache(maxsize=64)
def _google_origin(near: str, api_key: str) -> tuple[float, float] | None:
    """Resolve a user-supplied landmark/address through Google Places."""
    body = {
        "textQuery": near,
        "pageSize": 1,
        "languageCode": "zh-CN",
        "regionCode": "US",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.location",
    }
    request = urllib.request.Request(
        _GOOGLE_PLACES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError):
        try:
            payload = _httpx_json(
                _GOOGLE_PLACES_URL,
                headers={
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": "places.location",
                },
                json_body=body,
            )
        except (ValueError, httpx.HTTPError):
            return None
    places = payload.get("places") if isinstance(payload, dict) else None
    if not isinstance(places, list) or not places:
        return None
    location = places[0].get("location") if isinstance(places[0], dict) else None
    if not isinstance(location, dict):
        return None
    try:
        return float(location["latitude"]), float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        return None

_GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
_GOOGLE_PLACES_FIELDS = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.googleMapsUri",
        "places.websiteUri",
        "places.currentOpeningHours.openNow",
        "places.currentOpeningHours.weekdayDescriptions",
        "places.priceLevel",
        "places.photos",
    )
)

_INTENT_TERMS = {
    "walk_in": ("马上", "现在", "今天", "不用预约", "walk-in", "walk in"),
    "budget": ("便宜", "实惠", "预算", "不要太贵", "cheap", "affordable"),
    "mens": ("男士", "男生", "男友", "老公", "商务", "barber", "men", "mens"),
    "color": ("染", "漂", "挑染", "金发", "balayage", "blond", "highlight", "color"),
    "texture": ("卷发", "自然卷", "curly", "coily", "texture"),
    "short_womens": ("女士短发", "女生短发", "精灵剪", "pixie"),
    "premium": ("高端", "体验", "按摩", "服务好", "premium", "luxury"),
}

_INTENT_COLUMNS = {
    "walk_in": ("walk-in政策", "关键发现"),
    "budget": ("价格区间", "样本价格", "推荐标签", "关键发现"),
    "mens": ("性别定位", "擅长风格(带置信度)", "推荐标签"),
    "color": ("擅长风格(带置信度)", "招牌作品", "推荐标签"),
    "texture": ("发质覆盖", "擅长风格(带置信度)", "推荐标签"),
    "short_womens": ("擅长风格(带置信度)", "推荐标签"),
    "premium": ("商业模式", "价格区间", "推荐标签", "关键发现"),
}


def _home() -> Path:
    raw = os.environ.get("HONEYOS_HOME", "").strip()
    return Path(raw).expanduser().resolve() if raw else Path.home() / ".honeyos"


def _index_dir(home: Path | None = None) -> Path:
    return (home or _home()) / "data" / "local-life"


def _is_honeyos_runtime() -> bool:
    return os.environ.get("HONEYOS_RUNTIME_ID", "").startswith("honeyos-companion-")


def _available() -> bool:
    return _is_honeyos_runtime() and any(_index_dir().glob("*.csv"))


def _google_maps_available() -> bool:
    return _is_honeyos_runtime() and bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip())


def _compact(value: Any, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _first_clause(value: Any, limit: int = 240) -> str:
    text = _compact(value, limit * 2)
    if not text:
        return ""
    clause = re.split(r"(?:\s+[—–]\s+|;|；|\.\s+)", text, maxsplit=1)[0].strip()
    return _compact(clause, limit)


def _clean_address(value: Any) -> str:
    text = _compact(value, 280)
    return re.split(r"\s*(?:\(|—|–)\s*", text, maxsplit=1)[0].strip()


def _first_url(value: Any) -> str:
    text = str(value or "").strip()
    if text.casefold().startswith(("none", "未找到", "n/a")):
        return ""
    match = re.search(r"https?://[^\s;)]+", text, flags=re.IGNORECASE)
    return match.group(0).rstrip(".,") if match else ""


def _number(value: Any) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else None


def _trusted_number(value: Any) -> float | None:
    text = str(value or "")
    lowered = text.casefold()
    if any(marker in lowered for marker in ("未能核实", "not independently verified", "removed")):
        return None
    return _number(text)


def _int_number(value: Any) -> int | None:
    match = re.search(r"\d[\d,]*", str(value or ""))
    return int(match.group(0).replace(",", "")) if match else None


def _normalized_name(row: dict[str, str]) -> str:
    return _compact(row.get("店名") or row.get("name"), 180)


def _display_name(row: dict[str, str], meta: dict[str, Any]) -> str:
    canonical = _normalized_name(row)
    names = meta.get("display_names")
    if isinstance(names, dict):
        return _compact(names.get(canonical) or canonical, 120)
    return canonical


def _override(row: dict[str, str], meta: dict[str, Any], key: str) -> Any:
    overrides = meta.get("overrides")
    if not isinstance(overrides, dict):
        return None
    record = overrides.get(_normalized_name(row))
    return record.get(key) if isinstance(record, dict) else None


def _load_meta(csv_path: Path) -> dict[str, Any]:
    path = csv_path.with_suffix(".meta.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_indexes(home: Path | None = None) -> list[tuple[dict[str, str], dict[str, Any]]]:
    loaded: list[tuple[dict[str, str], dict[str, Any]]] = []
    for path in sorted(_index_dir(home).glob("*.csv")):
        meta = _load_meta(path)
        try:
            with path.open(newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    if isinstance(row, dict) and _normalized_name(row):
                        loaded.append((row, meta))
        except (OSError, csv.Error):
            continue
    return loaded


def _location_for(row: dict[str, str], meta: dict[str, Any]) -> tuple[float, float] | None:
    locations = meta.get("locations")
    if not isinstance(locations, dict):
        return None
    value = locations.get(_normalized_name(row))
    if not isinstance(value, dict):
        return None
    try:
        return float(value["lat"]), float(value["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def _default_origin(meta: dict[str, Any]) -> tuple[str, tuple[float, float] | None]:
    label = _compact(meta.get("default_near"), 180)
    value = meta.get("default_origin")
    if not isinstance(value, dict):
        return label, None
    try:
        return label, (float(value["lat"]), float(value["lon"]))
    except (KeyError, TypeError, ValueError):
        return label, None


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(value))


def _query_intents(query: str) -> set[str]:
    lowered = query.casefold()
    return {
        intent
        for intent, terms in _INTENT_TERMS.items()
        if any(term.casefold() in lowered for term in terms)
    }


def _row_text(row: dict[str, str], columns: tuple[str, ...] | None = None) -> str:
    values = row.values() if columns is None else (row.get(column, "") for column in columns)
    return " ".join(str(value or "") for value in values).casefold()


def _category_matches(query: str, category: str, meta: dict[str, Any]) -> bool:
    requested = category.strip().casefold()
    indexed = str(meta.get("category") or "").strip().casefold()
    if requested:
        return not indexed or requested == indexed
    if not indexed:
        return True
    terms = _CATEGORY_SYNONYMS.get(indexed, ())
    lowered = query.casefold()
    return any(term.casefold() in lowered for term in terms)


def _fit_signals(row: dict[str, str]) -> list[str]:
    raw = _compact(row.get("推荐标签"), 800)
    if not raw:
        return []
    chunks = [chunk.strip(" ·,，;；") for chunk in re.split(r"\s{1,}|[;；]", raw)]
    return [chunk for chunk in chunks if len(chunk) >= 2][:3]


def _score(
    row: dict[str, str],
    *,
    query: str,
    intents: set[str],
    origin: tuple[float, float] | None,
    location: tuple[float, float] | None,
) -> tuple[float, float | None]:
    score = 0.0
    full_text = _row_text(row)
    tokens = [token for token in re.split(r"[^\w\u4e00-\u9fff]+", query.casefold()) if len(token) >= 2]
    score += min(3.0, sum(0.35 for token in tokens if token in full_text))
    for intent in intents:
        intent_text = _row_text(row, _INTENT_COLUMNS[intent])
        if any(term.casefold() in intent_text for term in _INTENT_TERMS[intent]):
            score += 2.2
    if "walk_in" in intents:
        policy = str(row.get("walk-in政策") or "").casefold()
        if any(term in policy for term in ("walk-ins only", "walk-in only", "no appointment needed", "no appointments taken")):
            score += 2.4
        elif "walk-ins welcome" in policy:
            score += 0.7
        if "appointment only" in policy or "by appointment only" in policy:
            score -= 3.0
    if "budget" in intents:
        price_text = str(row.get("价格区间") or "").casefold()
        if any(term in price_text for term in ("$$$$", "$$$", "premium", "$115")):
            score -= 1.8
        elif any(term in price_text for term in ("$30", "$45", "$$ tier", "affordable")):
            score += 1.2
    if "color" in intents and "mens" not in intents:
        gender_text = str(row.get("性别定位") or "").casefold()
        if any(term in gender_text for term in ("men-only", "men only", "男士专属")):
            score -= 4.0
    rating = _trusted_number(row.get("Google评分")) or _trusted_number(row.get("Yelp评分"))
    if rating is not None and 0 <= rating <= 5:
        score += rating / 5
    reviews = _int_number(row.get("Google评论数")) or _int_number(row.get("Yelp评论数"))
    if reviews:
        score += min(0.8, math.log10(max(reviews, 1)) / 4)
    distance = None
    if origin is not None and location is not None:
        distance = _haversine_km(origin, location)
        score += 3.5 / (1 + distance)
    return score, distance


def _result(
    row: dict[str, str],
    *,
    meta: dict[str, Any],
    origin_label: str,
    distance_km: float | None,
    score: float,
) -> dict[str, Any]:
    name = _display_name(row, meta)
    address = _clean_address(row.get("地址"))
    destination = f"{name}, {address}" if address else name
    maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(destination)}"
    directions_url = ""
    if origin_label:
        directions_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={quote_plus(origin_label)}&destination={quote_plus(destination)}"
        )
    rating = _trusted_number(row.get("Google评分")) or _trusted_number(row.get("Yelp评分"))
    review_count = _int_number(row.get("Google评论数")) or _int_number(row.get("Yelp评论数"))
    return {
        "name": name,
        "address": address,
        "distance_km": round(distance_km, 2) if distance_km is not None else None,
        "price": _compact(_override(row, meta, "price") or _first_clause(row.get("价格区间"), 180), 220),
        "rating": rating,
        "review_count": review_count,
        "hours": _compact(_override(row, meta, "hours") or _first_clause(row.get("营业时间"), 220), 240),
        "walk_in": _compact(_override(row, meta, "walk_in") or _first_clause(row.get("walk-in政策"), 180), 200),
        "fit_signals": _override(row, meta, "fit_signals") or _fit_signals(row),
        "cautions": _compact(_override(row, meta, "cautions") or _first_clause(row.get("差评模式"), 220), 240),
        "maps_url": maps_url,
        "directions_url": directions_url,
        "booking_url": _first_url(row.get("预约链接")),
        "website_url": _first_url(row.get("官网")),
        "yelp_url": _first_url(row.get("Yelp链接")),
        "image_url": "",
        "rank_score": round(score, 3),
    }


def _google_places_search(
    *,
    query: str,
    near: str,
    limit: int,
    origin: tuple[float, float] | None,
    fetch_photo: bool = True,
) -> list[dict[str, Any]]:
    """Return public Places results without ever placing the API key in a URL."""
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        return []

    text_query = query if not near else f"{query} near {near}"
    body: dict[str, Any] = {
        "textQuery": text_query,
        "pageSize": limit,
        "languageCode": "zh-CN",
        "regionCode": "US",
    }
    # Text Search may otherwise return the landmark embedded in ``near`` as a
    # result (for example Tencent America when asking for a salon near the
    # Tencent office).  Apply a supported Places type whenever the request is
    # unambiguously categorical so every returned row is actually a salon.
    normalized_query = query.casefold()
    if any(term.casefold() in normalized_query for term in _CATEGORY_SYNONYMS["hair_salon"]):
        body["includedType"] = "hair_salon"
    if origin is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": origin[0], "longitude": origin[1]},
                "radius": 12000.0,
            }
        }
    request = urllib.request.Request(
        _GOOGLE_PLACES_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": _GOOGLE_PLACES_FIELDS,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.HTTPError, urllib.error.URLError) as exc:
        logger.info(
            "Google Places urllib request failed (%s); retrying with httpx",
            type(exc).__name__,
        )
        try:
            payload = _httpx_json(
                _GOOGLE_PLACES_URL,
                headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _GOOGLE_PLACES_FIELDS},
                json_body=body,
            )
        except (ValueError, httpx.HTTPError) as fallback_exc:
            logger.info("Google Places request failed: %s", type(fallback_exc).__name__)
            return []

    places = payload.get("places") if isinstance(payload, dict) else None
    if not isinstance(places, list):
        return []
    results: list[dict[str, Any]] = []
    photo_found_for_response = False
    for place in places[:limit]:
        if not isinstance(place, dict):
            continue
        display = place.get("displayName")
        name = display.get("text", "") if isinstance(display, dict) else ""
        name = _compact(name, 120)
        if not name:
            continue
        address = _compact(place.get("formattedAddress"), 220)
        location = place.get("location")
        place_location = None
        if isinstance(location, dict):
            try:
                place_location = (float(location["latitude"]), float(location["longitude"]))
            except (KeyError, TypeError, ValueError):
                pass
        distance = _haversine_km(origin, place_location) if origin and place_location else None
        opening = place.get("currentOpeningHours")
        open_now = opening.get("openNow") if isinstance(opening, dict) else None
        weekdays = opening.get("weekdayDescriptions") if isinstance(opening, dict) else None
        hours = ""
        if open_now is True:
            hours = "现在营业"
        elif open_now is False:
            hours = "现在未营业"
        if isinstance(weekdays, list) and weekdays:
            hours = f"{hours}；" if hours else ""
            hours += _compact(weekdays[0], 180)
        maps_url = _first_url(place.get("googleMapsUri"))
        if not maps_url:
            maps_url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(name + ', ' + address)}"
        directions_url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&origin={quote_plus(near)}&destination={quote_plus(name + ', ' + address)}"
            if near
            else ""
        )
        image_path = ""
        photo_attribution = ""
        photos = place.get("photos")
        if fetch_photo and not photo_found_for_response and isinstance(photos, list) and photos:
            # Google businesses commonly expose several photo resources, and
            # an individual resource may be stale or temporarily unavailable.
            # Try a few rather than treating the first failure as "no photo".
            for photo in photos[:3]:
                image_path, photo_attribution = _cache_google_photo(
                    photo, api_key=api_key, place_id=str(place.get("id") or name)
                )
                if image_path:
                    photo_found_for_response = True
                    break
        results.append(
            {
                "name": name,
                "address": address,
                "distance_km": round(distance, 2) if distance is not None else None,
                "price": _compact(str(place.get("priceLevel") or "").replace("PRICE_LEVEL_", ""), 80),
                "rating": place.get("rating"),
                "review_count": place.get("userRatingCount"),
                "hours": hours,
                "walk_in": "",
                "fit_signals": [],
                "cautions": "",
                "maps_url": maps_url,
                "directions_url": directions_url,
                "booking_url": "",
                "website_url": _first_url(place.get("websiteUri")),
                "yelp_url": "",
                "image_url": "",
                "image_path": image_path,
                "photo_attribution": photo_attribution,
                "rank_score": 0,
            }
        )
    return results


def _cache_google_photo(
    photo: dict[str, Any], *, api_key: str, place_id: str
) -> tuple[str, str]:
    name = str(photo.get("name") or "").strip()
    if not name.startswith("places/"):
        return "", ""
    digest = hashlib.sha256(f"{place_id}:{name}".encode()).hexdigest()[:20]
    target_dir = _home() / "cache" / "images"
    target = target_dir / f"local-life-{digest}.jpg"
    authors = photo.get("authorAttributions")
    attribution = "Google Maps"
    if isinstance(authors, list):
        labels = [
            _compact(item.get("displayName"), 80)
            for item in authors
            if isinstance(item, dict) and item.get("displayName")
        ]
        if labels:
            attribution = "Google Maps · " + "、".join(labels[:2])
    if target.is_file() and target.stat().st_size > 0:
        return str(target), attribution

    media_url = (
        f"https://places.googleapis.com/v1/{name}/media"
        "?maxWidthPx=1200&skipHttpRedirect=true"
    )
    metadata_request = urllib.request.Request(
        media_url,
        headers={"X-Goog-Api-Key": api_key},
    )
    for attempt in range(2):
        try:
            with urllib.request.urlopen(metadata_request, timeout=12) as response:
                metadata = json.loads(response.read().decode("utf-8"))
            photo_uri = _first_url(metadata.get("photoUri") if isinstance(metadata, dict) else "")
            if not photo_uri:
                return "", ""
            photo_request = urllib.request.Request(
                photo_uri, headers={"User-Agent": "HoneyOS/1.0"}
            )
            with urllib.request.urlopen(photo_request, timeout=15) as response:
                content = response.read(5 * 1024 * 1024 + 1)
            if not content or len(content) > 5 * 1024 * 1024:
                return "", ""
            target_dir.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            target.chmod(0o600)
            return str(target), attribution
        except urllib.error.HTTPError as exc:
            # Client/permission failures are deterministic; another photo
            # resource may still work, so return and let the caller try it.
            logger.info("Google Places photo unavailable (HTTP %s)", exc.code)
            if exc.code < 500 and exc.code != 429:
                return "", ""
            if attempt == 0:
                continue
            break
        except (OSError, ValueError, urllib.error.URLError) as exc:
            if attempt == 0:
                continue
            logger.info("Google Places photo download failed: %s", type(exc).__name__)
    try:
        metadata = _httpx_json(
            media_url,
            headers={"X-Goog-Api-Key": api_key},
        )
        photo_uri = _first_url(metadata.get("photoUri"))
        if not photo_uri:
            return "", ""
        content = _httpx_bytes(photo_uri, headers={"User-Agent": "HoneyOS/1.0"})
        if not content or len(content) > 5 * 1024 * 1024:
            return "", ""
        target_dir.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o600)
        return str(target), attribution
    except (ValueError, httpx.HTTPError) as exc:
        logger.info("Google Places photo httpx fallback failed: %s", type(exc).__name__)
    return "", ""


def search_local_life(
    *,
    query: str,
    category: str = "",
    near: str = "",
    limit: int = 3,
    home: Path | None = None,
) -> dict[str, Any]:
    query = _compact(query, 800)
    if not query:
        return {"success": False, "error": "query is required"}
    try:
        bounded_limit = max(1, min(5, int(limit)))
    except (TypeError, ValueError):
        bounded_limit = 3

    entries = _load_indexes(home)
    candidates: list[tuple[float, dict[str, Any]]] = []
    intents = _query_intents(query)
    default_label = ""
    default_origin = None
    for row, meta in entries:
        if not _category_matches(query, category, meta):
            continue
        if not default_label:
            default_label, default_origin = _default_origin(meta)
        origin_label = near.strip() or default_label
        # A free-text, non-default origin is retained for directions, but not
        # silently geocoded here. The existing maps capability can calculate a
        # live route when the user needs exact travel time.
        origin = default_origin if not near.strip() or near.strip() == default_label else None
        location = _location_for(row, meta)
        score, distance = _score(
            row,
            query=query,
            intents=intents,
            origin=origin,
            location=location,
        )
        candidates.append(
            (
                score,
                _result(
                    row,
                    meta=meta,
                    origin_label=origin_label,
                    distance_km=distance,
                    score=score,
                ),
            )
        )

    candidates.sort(key=lambda item: (-item[0], item[1]["name"]))
    results = [item[1] for item in candidates[:bounded_limit]]
    used_google_fallback = False
    media_enriched = False
    if not results:
        fallback_near = near.strip() or default_label
        results = _google_places_search(
            query=query,
            near=fallback_near,
            limit=bounded_limit,
            origin=default_origin if not near.strip() or near.strip() == default_label else None,
        )
        used_google_fallback = bool(results)
    elif os.environ.get("GOOGLE_MAPS_API_KEY", "").strip():
        # The private index remains authoritative. Google is queried only to
        # enrich the first recommendation with a native photo/current place
        # link, never to replace the locally-ranked recommendation list.
        first = results[0]
        enrichment = _google_places_search(
            query=f"{first['name']} {first['address']}",
            near=near.strip() or default_label,
            limit=1,
            origin=default_origin if not near.strip() or near.strip() == default_label else None,
        )
        if enrichment:
            live = enrichment[0]
            if live.get("image_path"):
                first["image_path"] = live["image_path"]
                first["photo_attribution"] = live.get("photo_attribution", "Google Maps")
                media_enriched = True
            if live.get("maps_url"):
                first["maps_url"] = live["maps_url"]
            if not first.get("website_url") and live.get("website_url"):
                first["website_url"] = live["website_url"]
    return {
        "success": True,
        "query": query,
        "near": near.strip() or default_label,
        "results": results,
        "fallback_required": not bool(results),
        "live_lookup_used": used_google_fallback,
        "media_enriched": media_enriched,
        "fallback_hint": (
            "No private local result matched. Continue with the maps capability, then web "
            "search only if current hours, photos, or booking details still need verification."
            if not results
            else ""
        ),
    }


def search_google_places(
    *, query: str, near: str, limit: int = 3
) -> dict[str, Any]:
    """Search Google Places directly without a terminal or web-search detour."""
    query = _compact(query, 800)
    near = _compact(near, 300)
    if not query:
        return {"success": False, "error": "query is required", "fallback_required": False}
    if not near:
        return {"success": False, "error": "near is required", "fallback_required": False}
    if not os.environ.get("GOOGLE_MAPS_API_KEY", "").strip():
        return {
            "success": False,
            "error": "Google Places is not configured",
            "fallback_required": True,
        }
    try:
        bounded_limit = max(1, min(5, int(limit)))
    except (TypeError, ValueError):
        bounded_limit = 3
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    origin = _google_origin(near, api_key)
    results = _google_places_search(
        query=query,
        near=near,
        limit=bounded_limit,
        origin=origin,
    )
    has_photo = any(item.get("image_path") for item in results)
    return {
        "success": bool(results),
        "provider": "google_places_api",
        "query": query,
        "near": near,
        "results": results,
        "fallback_required": not bool(results),
        "photo_fallback_required": bool(results) and not has_photo,
        "fallback_hint": (
            "Google Places returned no usable result. A public web or Yelp search may be used now."
            if not results
            else ""
        ),
    }


def _handler(args: dict[str, Any], **_: object) -> str:
    result = search_local_life(
        query=str(args.get("query") or ""),
        category=str(args.get("category") or ""),
        near=str(args.get("near") or ""),
        limit=args.get("limit", 3),
    )
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


def _google_maps_handler(args: dict[str, Any], **_: object) -> str:
    result = search_google_places(
        query=str(args.get("query") or ""),
        near=str(args.get("near") or ""),
        limit=args.get("limit", 3),
    )
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))


registry.register(
    name="local_life_search",
    toolset="local_life",
    schema=LOCAL_LIFE_SEARCH_SCHEMA,
    handler=_handler,
    check_fn=_available,
    emoji="📍",
)

registry.register(
    name="google_maps_search",
    toolset="local_life",
    schema=GOOGLE_MAPS_SEARCH_SCHEMA,
    handler=_google_maps_handler,
    check_fn=_google_maps_available,
    emoji="🗺️",
)
