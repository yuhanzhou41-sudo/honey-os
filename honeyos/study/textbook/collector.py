"""Targeted section collector (L3): open one section, scroll, OCR, stop at boundary.

Only the requested section is captured. Screenshots are written into the cache
``temp`` directory and deleted immediately after each OCR call, so disk usage is
bounded by a single frame plus the extracted text.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import xml.etree.ElementTree as ET

from .outline import BookOutline, SECTION_HEADING, CHAPTER_HEADING, SectionRef, normalize

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_CHROME = re.compile(
    r"^(下拉加载上一页|上拉加载下一页|正在加载|加载中|返回|目录|书签|笔记|书架|人卫|"
    r"上一页|下一页|退出|分享|搜索|加入书架|夜间|字号|设置|更多|收藏|评论|举报|"
    r"首页|学习|我的|学习中心|教材列表)$"
)
_PAGE_NUMBER = re.compile(r"^[-—–\s]*\d{1,4}[-—–\s]*$")
_ICON_PREFIX = re.compile(r"^(?:icon|img|image)[\s:：\-_]+", re.IGNORECASE)
# The reading app keeps a navigation drawer in the same tree; its front matter
# marks the end of real body text.
_FRONT_MATTER = {
    "封面", "版权页", "数字教材编委会", "修订说明", "前言", "序言", "后记",
    "参考文献", "目录", "附录", "索引", "编写说明",
}
_SKIP_LINES = {"<未命名>", "未命名", "加载中"}


class TextbookCollectionError(RuntimeError):
    pass


class TextbookNavigationError(TextbookCollectionError):
    pass


@dataclass(frozen=True)
class CollectResult:
    text: str
    screens: int
    stop_reason: str
    duration_s: float
    lines: int
    mode: str = "ocr"
    anchored: bool = True


def clean_lines(raw: str) -> list[str]:
    """Drop app chrome, page numbers and OCR noise from one screenshot."""
    lines: list[str] = []
    for piece in re.split(r"[\n\r]+", str(raw or "")):
        line = re.sub(r"[ \t\u3000]+", " ", piece).strip()
        if not line or _CHROME.match(line) or _PAGE_NUMBER.match(line):
            continue
        if line in lines[-1:]:
            continue
        lines.append(line)
    return lines


def merge_screens(collected: list[str], screen: list[str], *, min_overlap: int = 2) -> tuple[list[str], int]:
    """Append ``screen`` minus the lines already seen at the tail of ``collected``."""
    if not collected:
        return list(screen), len(screen)
    if not screen:
        return [], 0
    limit = min(len(collected), len(screen), 60)
    for size in range(limit, min_overlap - 1, -1):
        if collected[-size:] == screen[:size]:
            return screen[size:], size
    strip = lambda rows: [re.sub(r"\s+", "", row) for row in rows]
    left, right = strip(collected), strip(screen)
    for size in range(limit, min_overlap - 1, -1):
        if left[-size:] == right[:size]:
            return screen[size:], size
    return list(screen), 0


def find_boundary(lines: list[str], stop_titles: list[str], *, current_title: str = "") -> int | None:
    """Index of the first line that starts the next section/chapter."""
    stops = {normalize(item) for item in stop_titles if item}
    current = normalize(current_title)
    for index, line in enumerate(lines):
        value = line.strip()
        key = normalize(value)
        if not key or (current and key == current):
            continue
        if key in stops:
            return index
        if SECTION_HEADING.match(value) or CHAPTER_HEADING.match(value):
            return index
    return None


def find_text_center(dump: str, text: str) -> tuple[int, int] | None:
    target = normalize(text)
    try:
        root = ET.fromstring(dump)
    except ET.ParseError:
        return None
    for node in root.iter():
        label = normalize(node.get("text") or node.get("content-desc") or "")
        if target and target in label:
            match = _BOUNDS.fullmatch(str(node.get("bounds") or "").strip())
            if match:
                x1, y1, x2, y2 = (int(part) for part in match.groups())
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def extract_dump_lines(dump: str) -> list[str]:
    """Readable body lines from a UI dump, in document order.

    The reading app exposes rendered text through the accessibility tree, which
    is much more accurate than screenshot OCR. One-character fragments (vertical
    cover labels) and app chrome are dropped.
    """
    try:
        root = ET.fromstring(dump)
    except ET.ParseError:
        return []
    lines: list[str] = []
    for node in root.iter():
        raw = node.get("text") or node.get("content-desc") or ""
        for piece in re.split(r"[\n\r]+", raw):
            line = _ICON_PREFIX.sub("", re.sub(r"[ \t\u3000]+", " ", str(piece or "")).strip())
            if not line or line in _SKIP_LINES or _CHROME.match(line) or _PAGE_NUMBER.match(line) or len(line) == 1:
                continue
            if line in lines[-1:]:
                continue
            lines.append(line)
    return lines


class SectionCollector:
    def __init__(
        self,
        bridge,
        ocr,
        temp_dir: Path | str,
        *,
        max_screens: int = 60,
        settle_seconds: float = 1.2,
        scroll_ratio: float = 0.72,
        min_overlap: int = 2,
    ):
        self.bridge = bridge
        self.ocr = ocr
        self.temp_dir = Path(temp_dir)
        self.max_screens = int(max_screens)
        self.settle_seconds = float(settle_seconds)
        self.scroll_ratio = min(0.9, max(0.3, float(scroll_ratio)))
        self.min_overlap = int(min_overlap)

    def _open(self, book: BookOutline, section: SectionRef) -> None:
        tap = section.tap
        if tap is None:
            try:
                dump = self.bridge.dump_ui()
            except Exception as exc:  # pragma: no cover - device specific
                raise TextbookNavigationError(f"无法读取当前界面：{exc}") from exc
            tap = find_text_center(dump, section.title)
            if tap is None:
                # On the study centre the section is not visible; open the book first.
                book_spot = find_text_center(dump, book.title)
                if book_spot is not None:
                    self.bridge.tap(int(book_spot[0]), int(book_spot[1]))
                    if self.settle_seconds > 0:
                        time.sleep(self.settle_seconds)
                    dump = self.bridge.dump_ui()
                    tap = find_text_center(dump, section.title)
        if tap is None:
            raise TextbookNavigationError(
                f"当前界面没有找到“{section.title}”，请先回到目录页后再采集。"
            )
        self.bridge.tap(int(tap[0]), int(tap[1]))
        if self.settle_seconds > 0:
            time.sleep(self.settle_seconds)

    def _scroll(self) -> None:
        try:
            width, height = self.bridge.screen_size()
        except Exception:  # pragma: no cover - device specific
            width, height = 1080, 1920
        x = width // 2
        start = int(height * 0.78)
        end = int(height * (0.78 - self.scroll_ratio))
        self.bridge.swipe(x, start, x, end, 320)
        if self.settle_seconds > 0:
            time.sleep(self.settle_seconds)

    def collect(
        self,
        book: BookOutline,
        section: SectionRef,
        *,
        progress: Callable[[dict], None] | None = None,
    ) -> CollectResult:
        result = self._collect_ui(book, section, progress)
        if result is not None:
            return result
        return self._collect_ocr(book, section, progress)

    def _heading_index(self, lines: list[str], section: SectionRef) -> int | None:
        target = normalize(section.title)
        for index, line in enumerate(lines):
            key = normalize(line)
            if key == target or (target and key.endswith(target) and len(key) <= len(target) + 12):
                return index
        return None

    def _collect_ui(
        self,
        book: BookOutline,
        section: SectionRef,
        progress: Callable[[dict], None] | None,
    ) -> CollectResult | None:
        """Primary path: read the accessibility tree; no screenshots at all."""
        started = time.monotonic()
        dump = self.bridge.dump_ui()
        lines = extract_dump_lines(dump)
        heading = self._heading_index(lines, section)
        if heading is None:
            spot = find_text_center(dump, section.title)
            if spot is None:
                book_spot = find_text_center(dump, book.title)
                if book_spot is not None:
                    self.bridge.tap(int(book_spot[0]), int(book_spot[1]))
                    if self.settle_seconds > 0:
                        time.sleep(self.settle_seconds)
                    dump = self.bridge.dump_ui()
                    lines = extract_dump_lines(dump)
                    heading = self._heading_index(lines, section)
                    if heading is None:
                        spot = find_text_center(dump, section.title)
            if spot is not None:
                self.bridge.tap(int(spot[0]), int(spot[1]))
                if self.settle_seconds > 0:
                    time.sleep(self.settle_seconds)
                dump = self.bridge.dump_ui()
                lines = extract_dump_lines(dump)
                heading = self._heading_index(lines, section)
        if heading is None:
            return None
        anchored = True
        lines = lines[heading + 1:]

        collected: list[str] = []
        stop_titles = book.next_titles(section.section_id)
        stop_reason = "max_screens"
        screens = 0
        stall = 0
        for _ in range(max(1, min(self.max_screens, 12))):
            screens += 1
            cut = find_boundary(lines, stop_titles, current_title=section.title)
            front = next(
                (index for index, line in enumerate(lines) if normalize(line) in _FRONT_MATTER),
                None,
            )
            if cut is not None or front is not None:
                limit = cut if cut is not None else front
                if front is not None and (cut is None or front < cut):
                    limit = front
                lines = lines[:limit]
                stop_reason = "boundary"
            new_lines, _ = merge_screens(collected, lines, min_overlap=self.min_overlap)
            collected.extend(new_lines)
            if progress is not None:
                progress({"mode": "ui_text", "screens": screens, "lines": len(collected), "stop": stop_reason})
            if stop_reason == "boundary":
                break
            if not new_lines:
                stop_reason = "stalled"
                break
            self._scroll()
            lines = extract_dump_lines(self.bridge.dump_ui())
            if not lines:
                stop_reason = "no_text"
                break

        text = "\n".join(collected).strip()
        if not text:
            return None
        return CollectResult(
            text=text,
            screens=screens,
            stop_reason=stop_reason,
            duration_s=round(time.monotonic() - started, 2),
            lines=len(collected),
            mode="ui_text",
            anchored=anchored,
        )

    def _collect_ocr(
        self,
        book: BookOutline,
        section: SectionRef,
        progress: Callable[[dict], None] | None,
    ) -> CollectResult:
        started = time.monotonic()
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self._open(book, section)

        collected: list[str] = []
        stall = 0
        screens = 0
        stop_reason = "max_screens"
        stop_titles = book.next_titles(section.section_id)

        for index in range(self.max_screens):
            shot = self.temp_dir / f"{section.section_id}_{index:03d}.png"
            try:
                self.bridge.screencap(shot)
                raw = self.ocr.recognize(shot)
            finally:
                try:
                    shot.unlink()
                except FileNotFoundError:
                    pass

            screens += 1
            lines = clean_lines(raw)
            if not lines:
                stall += 1
                if stall >= 2:
                    stop_reason = "no_text"
                    break
                self._scroll()
                continue
            stall = 0

            cut = find_boundary(lines, stop_titles, current_title=section.title)
            if cut is not None:
                lines = lines[:cut]
                stop_reason = "boundary"

            new_lines, _ = merge_screens(collected, lines, min_overlap=self.min_overlap)
            collected.extend(new_lines)
            if progress is not None:
                progress({"mode": "ocr", "screens": screens, "lines": len(collected), "stop": stop_reason})

            if stop_reason == "boundary":
                break
            if not new_lines and collected:
                stall += 1
                if stall >= 2:
                    stop_reason = "stalled"
                    break
            self._scroll()

        text = "\n".join(collected).strip()
        elapsed = round(time.monotonic() - started, 2)
        if not text:
            raise TextbookCollectionError(
                "没有识别到正文。请确认已进入章节正文页，并检查 OCR/视觉模型配置。"
            )
        return CollectResult(
            text=text,
            screens=screens,
            stop_reason=stop_reason,
            duration_s=elapsed,
            lines=len(collected),
            mode="ocr",
        )
