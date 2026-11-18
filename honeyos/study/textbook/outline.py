"""Chapter outline parsing and demand-to-chapter matching.

The outline is built from the reading app's UI hierarchy (headings are real
widgets even though body text is not), never from the whole book body.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any
import xml.etree.ElementTree as ET

CHAPTER_HEADING = re.compile(r"^第[一二三四五六七八九十百零〇两]+章")
SECTION_HEADING = re.compile(r"^第[一二三四五六七八九十百零〇两]+节")
_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9]{2,}")


class TextbookOutlineError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(text: str) -> str:
    return _SPACE.sub("", str(text or "")).casefold()


def make_section_id(book_id: str, chapter: str, title: str) -> str:
    digest = sha1(f"{book_id}|{chapter}|{title}".encode("utf-8")).hexdigest()
    return f"sec_{digest[:12]}"


@dataclass(frozen=True)
class SectionRef:
    section_id: str
    title: str
    chapter: str = ""
    sequence: int = 0
    tap: tuple[int, int] | None = None

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(part for part in (self.chapter, self.title) if part)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tap"] = list(self.tap) if self.tap else None
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SectionRef":
        tap = raw.get("tap")
        return cls(
            section_id=str(raw["section_id"]),
            title=str(raw["title"]),
            chapter=str(raw.get("chapter") or ""),
            sequence=int(raw.get("sequence") or 0),
            tap=(int(tap[0]), int(tap[1])) if isinstance(tap, (list, tuple)) and len(tap) == 2 else None,
        )


@dataclass(frozen=True)
class BookOutline:
    book_id: str
    title: str
    sections: tuple[SectionRef, ...] = field(default_factory=tuple)
    updated_at: str = field(default_factory=_now)
    source: dict[str, Any] = field(default_factory=dict)

    def section(self, section_id: str) -> SectionRef:
        for item in self.sections:
            if item.section_id == section_id:
                return item
        raise KeyError(section_id)

    def next_titles(self, section_id: str, limit: int = 3) -> list[str]:
        """Titles that mark the end of the requested section."""
        titles: list[str] = []
        found = False
        for item in self.sections:
            if found and item.title not in titles:
                titles.append(item.title)
                if len(titles) >= limit:
                    break
            if item.section_id == section_id:
                found = True
        current = self.section(section_id)
        if current.chapter:
            titles.append(current.chapter)
        return titles

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": 1,
            "book_id": self.book_id,
            "title": self.title,
            "updated_at": self.updated_at,
            "source": dict(self.source),
            "sections": [item.to_dict() for item in self.sections],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BookOutline":
        if int(raw.get("format_version", 1)) != 1:
            raise TextbookOutlineError("unsupported textbook index format")
        sections = raw.get("sections")
        if not isinstance(sections, list):
            raise TextbookOutlineError("textbook index has no sections")
        return cls(
            book_id=str(raw["book_id"]),
            title=str(raw.get("title") or raw["book_id"]),
            sections=tuple(SectionRef.from_dict(item) for item in sections if item.get("section_id")),
            updated_at=str(raw.get("updated_at") or _now()),
            source=dict(raw.get("source") or {}),
        )


def _clean_line(value: str) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def _center(bounds: str) -> tuple[int, int] | None:
    match = _BOUNDS.fullmatch(str(bounds or "").strip())
    if match is None:
        return None
    x1, y1, x2, y2 = (int(part) for part in match.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def parse_outline_from_ui_dump(
    dump: str, *, book_id: str, title: str = "", source: dict[str, Any] | None = None
) -> BookOutline:
    """Extract chapter/section headings and their tap points from a UI dump."""
    if not str(dump or "").strip():
        raise TextbookOutlineError("UI dump 为空，请先打开教材目录页再采集。")
    try:
        root = ET.fromstring(dump)
    except ET.ParseError as exc:
        raise TextbookOutlineError("无法解析 UI dump XML") from exc

    sections: list[SectionRef] = []
    seen: set[str] = set()
    chapter = ""
    for node in root.iter():
        label = _clean_line(node.get("text") or node.get("content-desc") or "")
        if not label:
            continue
        for line in re.split(r"[\n\r]+", label):
            line = _clean_line(line)
            if not line:
                continue
            if CHAPTER_HEADING.match(line):
                chapter = line
                continue
            if not SECTION_HEADING.match(line):
                continue
            key = normalize(line)
            if key in seen:
                continue
            seen.add(key)
            sections.append(
                SectionRef(
                    section_id=make_section_id(book_id, chapter, line),
                    title=line,
                    chapter=chapter,
                    sequence=len(sections) + 1,
                    tap=_center(node.get("bounds") or ""),
                )
            )
    if not sections:
        raise TextbookOutlineError("UI 树里没有找到“第X节”标题，请确认当前在教材目录页。")
    return BookOutline(
        book_id=book_id,
        title=title or book_id,
        sections=tuple(sections),
        source=dict(source or {}),
    )


def parse_outline_from_text(
    text: str, *, book_id: str, title: str = "", source: dict[str, Any] | None = None
) -> BookOutline:
    """Parse an OCR/plain-text table of contents (used when the dump lacks headings)."""
    sections: list[SectionRef] = []
    seen: set[str] = set()
    chapter = ""
    for raw in re.split(r"[\n\r]+", str(text or "")):
        line = _clean_line(raw)
        if not line:
            continue
        if CHAPTER_HEADING.match(line):
            chapter = line
            continue
        if not SECTION_HEADING.match(line):
            continue
        key = normalize(line)
        if key in seen:
            continue
        seen.add(key)
        sections.append(
            SectionRef(
                section_id=make_section_id(book_id, chapter, line),
                title=line,
                chapter=chapter,
                sequence=len(sections) + 1,
            )
        )
    if not sections:
        raise TextbookOutlineError("目录文本里没有找到“第X节”标题。")
    return BookOutline(
        book_id=book_id,
        title=title or book_id,
        sections=tuple(sections),
        source=dict(source or {}),
    )


def _grams(value: str, size: int = 2) -> set[str]:
    if len(value) < size:
        return {value} if value else set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def score_section(query: str, section: SectionRef) -> float:
    q = normalize(query)
    if not q:
        return 0.0
    title = normalize(section.title)
    chapter = normalize(section.chapter)
    if q in title:
        return 1.0
    if q in chapter:
        return 0.85
    grams = _grams(q)
    haystack = f"{chapter}{title}"
    hits = sum(1 for gram in grams if gram in haystack)
    if hits < 2:
        words = [word for word in _WORD.findall(str(query).casefold()) if word in haystack]
        return 0.6 if words else 0.0
    return round(min(0.8, 0.4 + 0.4 * hits / max(1, len(grams))), 3)


def locate_sections(
    query: str, outline: BookOutline, *, limit: int = 3, min_score: float = 0.3
) -> list[tuple[SectionRef, float]]:
    """Return the best matching sections for a study need, best first."""
    scored = [(item, score_section(query, item)) for item in outline.sections]
    scored = [(item, score) for item, score in scored if score >= min_score]
    scored.sort(key=lambda pair: (-pair[1], pair[0].sequence))
    return scored[: max(1, int(limit))]


def with_tap(section: SectionRef, tap: tuple[int, int] | None) -> SectionRef:
    return replace(section, tap=tap) if tap else section
