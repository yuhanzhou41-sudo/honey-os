from __future__ import annotations

import json

from honeyos.gateway.run import (
    _collect_auto_append_media_tags,
    _collect_history_media_paths,
)


def _maps_turn(call_id: str, image_path: str):
    return [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": call_id, "function": {"name": "google_maps_search"}}
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "content": json.dumps(
                {
                    "success": True,
                    "provider": "google_places_api",
                    "results": [{"name": "Demo", "image_path": image_path}],
                }
            ),
        },
    ]


def test_google_maps_photo_is_auto_appended_without_model_media_directive():
    messages = _maps_turn("maps-1", "/tmp/google-place.jpg")

    tags, voice = _collect_auto_append_media_tags(messages)

    assert tags == ["MEDIA:/tmp/google-place.jpg"]
    assert voice is False


def test_latest_google_maps_refinement_supplies_the_single_photo():
    messages = _maps_turn("maps-1", "/tmp/broad.jpg") + _maps_turn(
        "maps-2", "/tmp/refined.jpg"
    )

    tags, _ = _collect_auto_append_media_tags(messages)

    assert tags == ["MEDIA:/tmp/refined.jpg"]


def test_google_maps_photo_in_history_is_not_resent_automatically():
    history = _maps_turn("maps-old", "/tmp/already-sent.jpg")
    paths = _collect_history_media_paths(history)

    tags, _ = _collect_auto_append_media_tags(
        _maps_turn("maps-new", "/tmp/already-sent.jpg"),
        history_media_paths=paths,
    )

    assert paths == {"/tmp/already-sent.jpg"}
    assert tags == []
