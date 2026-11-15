from pathlib import Path

import pytest
from PIL import Image

from honeyos.companion.stickers import (
    StickerLimitReached,
    StickerStore,
    StickerValidationError,
)


def _write_gif(path: Path, color: str = "red") -> Path:
    Image.new("RGB", (24, 24), color=color).save(path, format="GIF")
    return path


def _write_png(path: Path, color: str = "blue") -> Path:
    Image.new("RGBA", (24, 24), color=color).save(path, format="PNG")
    return path


def test_sticker_store_add_list_use_delete(tmp_path):
    store = StickerStore(tmp_path / "stickers", limit=4, warning_threshold=3)
    source = _write_gif(tmp_path / "happy.gif")
    item = store.add_file(source, original_name="happy.gif", tag="happy")
    assert store.status()["count"] == 1
    assert store.list(tag="happy")[0]["id"] == item["id"]
    used = store.mark_used(item["id"])
    assert used and used["usage_count"] == 1
    media = store.media(item["id"])
    assert media and media[0].is_file()
    preview = store.preview(item["id"])
    assert preview and preview[0].is_file()
    assert preview[0].suffix == ".webp"
    assert store.delete(item["id"])
    assert store.status()["count"] == 0
    assert not preview[0].exists()


def test_sticker_store_warning_and_hard_limit(tmp_path):
    store = StickerStore(tmp_path / "stickers", limit=2, warning_threshold=1)
    store.add_file(_write_gif(tmp_path / "one.gif", "red"), original_name="one.gif", tag="awkward")
    assert store.status()["warning"] is True
    assert store.status()["full"] is False
    store.add_file(_write_gif(tmp_path / "two.gif", "green"), original_name="two.gif", tag="happy")
    assert store.status()["full"] is True
    with pytest.raises(StickerLimitReached):
        store.add_file(_write_gif(tmp_path / "three.gif", "blue"), original_name="three.gif", tag="sad")


def test_sticker_store_rejects_wrong_magic_or_tag(tmp_path):
    store = StickerStore(tmp_path / "stickers")
    bad = tmp_path / "bad.gif"
    bad.write_bytes(b"not-a-gif")
    with pytest.raises(StickerValidationError):
        store.add_file(bad, original_name="bad.gif", tag="happy")
    good = _write_gif(tmp_path / "good.gif")
    with pytest.raises(StickerValidationError):
        store.add_file(good, original_name="good.gif", tag="unknown")


def test_sticker_store_rejects_extension_mismatch(tmp_path):
    store = StickerStore(tmp_path / "stickers")
    actual_png = _write_png(tmp_path / "wrong.gif")
    with pytest.raises(StickerValidationError):
        store.add_file(actual_png, original_name="wrong.gif", tag="happy")


def test_sticker_store_sorting_is_bounded(tmp_path):
    store = StickerStore(tmp_path / "stickers", limit=6, warning_threshold=5)
    ids = []
    for index, color in enumerate(("red", "green", "blue")):
        item = store.add_file(
            _write_gif(tmp_path / f"{index}.gif", color),
            original_name=f"{index}.gif",
            tag="happy",
        )
        ids.append(item["id"])
    store.mark_used(ids[0])
    store.mark_used(ids[0])
    least = store.list(tag="happy", sort="least_used", limit=2)
    assert len(least) == 2
    assert least[0]["usage_count"] == 0
