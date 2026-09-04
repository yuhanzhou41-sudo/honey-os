from __future__ import annotations

import argparse

from honeyos.plugins.platforms.photon.adapter import _split_local_life_richlinks


def test_photon_setup_parser_accepts_existing_project_id():
    from honeyos.plugins.platforms.photon.cli import register_cli

    parser = argparse.ArgumentParser()
    register_cli(parser)
    args = parser.parse_args(
        [
            "setup",
            "--project-id",
            "11111111-2222-4333-8444-555555555555",
            "--skip-sidecar-install",
        ]
    )

    assert args.project_id == "11111111-2222-4333-8444-555555555555"
    assert args.skip_sidecar_install is True


def test_local_life_urls_are_split_into_native_richlink_cards():
    maps = "https://www.google.com/maps/search/?api=1&query=Demo"
    yelp = "https://www.yelp.com/biz/demo-palo-alto"
    body, links = _split_local_life_richlinks(
        f"推荐这家，评分 4.8。\n\n{maps}\n{yelp}"
    )

    assert body == "推荐这家，评分 4.8。"
    assert links == [maps, yelp]


def test_embedded_and_markdown_links_stay_in_the_text_body():
    raw = "地图：https://www.google.com/maps/search/?api=1&query=Demo"
    markdown = "[地图](https://www.google.com/maps/search/?api=1&query=Demo)"

    body, links = _split_local_life_richlinks(f"{raw}\n{markdown}")

    assert body == f"{raw}\n{markdown}"
    assert links == []
