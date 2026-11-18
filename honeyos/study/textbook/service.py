"""Application layer for on-demand textbook collection.

Flow: 需求定位 (locate) -> 定点采集 (collect) -> 文本缓存 (cache) ->
Study 资料供给 (resource + FTS) -> 复课后清理 (release).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .android_bridge import AndroidBridge
from .cache import DEFAULT_MAX_BYTES, SectionCache, SectionRecord
from .collector import SectionCollector
from .index_store import TextbookBookNotFoundError, TextbookIndexStore
from .ocr import make_default_ocr
from .outline import (
    BookOutline,
    SectionRef,
    TextbookOutlineError,
    locate_sections,
    make_section_id,
    normalize,
    merge_toc_dumps,
    parse_outline_from_text,
    parse_outline_from_ui_dump,
    parse_toc_from_ui_dump,
)
from .retention import TextbookRetention


class TextbookServiceError(RuntimeError):
    pass


def default_textbook_root() -> Path:
    configured = os.environ.get("HONEYOS_TEXTBOOK_ROOT")
    if configured:
        return Path(configured).expanduser()
    if os.name == "nt":
        drive = os.environ.get("HONEYOS_TEXTBOOK_DRIVE", "E:")
        return Path(drive) / "HoneyOS-Data" / "Textbook"
    return Path("/mnt/e/HoneyOS-Data/Textbook")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TextbookService:
    """Coordinates index, collector, cache and retention for one profile."""

    def __init__(
        self,
        study=None,
        *,
        root: Path | str | None = None,
        bridge=None,
        ocr=None,
        max_cache_bytes: int | None = None,
    ):
        self._study = study
        self.root = Path(root or default_textbook_root()).expanduser()
        self.bridge = bridge
        self.ocr = ocr
        self.index = TextbookIndexStore(self.root)
        self.cache = SectionCache(self.root, max_bytes=max_cache_bytes or DEFAULT_MAX_BYTES)
        self.retention = TextbookRetention(self.cache, self.index)

    @property
    def study(self):
        if self._study is None:
            from honeyos.study.service import StudyService

            self._study = StudyService()
        return self._study

    # -- L1: outline ---------------------------------------------------
    def save_outline(self, outline: BookOutline) -> BookOutline:
        return self.index.save(outline)

    def sync_outline_from_dump(
        self, book_id: str, dump: str, *, title: str = "", package: str = ""
    ) -> BookOutline:
        outline = parse_outline_from_ui_dump(
            dump,
            book_id=book_id,
            title=title,
            source={"kind": "ui_dump", "package": package, "captured_at": _now()},
        )
        return self.index.save(outline)

    def sync_outline_from_text(
        self, book_id: str, text: str, *, title: str = "", source: str = "toc_text"
    ) -> BookOutline:
        outline = parse_outline_from_text(
            text, book_id=book_id, title=title, source={"kind": source, "captured_at": _now()}
        )
        return self.index.save(outline)

    def sync_outline_from_device(
        self, book_id: str, *, title: str = "", bridge=None
    ) -> BookOutline:
        """Open the app's TOC drawer, capture chapters (and sections if expanded)."""
        active = bridge or self.bridge
        if active is None:
            active = AndroidBridge()
        source = {"kind": "device_toc", "captured_at": _now()}
        if hasattr(active, "capture_toc"):
            outline = merge_toc_dumps(
                active.capture_toc(), book_id=book_id, title=title, source=source
            )
        else:
            dump = active.expand_toc() if hasattr(active, "expand_toc") else active.open_toc() if hasattr(active, "open_toc") else active.dump_ui()
            outline = parse_toc_from_ui_dump(dump, book_id=book_id, title=title, source=source)
        if not outline.sections:
            try:
                existing = self.index.load(book_id)
            except TextbookBookNotFoundError:
                existing = None
            if existing is not None and existing.sections:
                outline = BookOutline(
                    book_id=outline.book_id,
                    title=outline.title or existing.title,
                    sections=existing.sections,
                    source=outline.source,
                )
        return self.index.save(outline)

    def list_books(self) -> list[dict[str, Any]]:
        return self.index.list_books()

    def get_outline(self, book_id: str) -> BookOutline:
        return self.index.load(book_id)

    # -- L2: demand lookup --------------------------------------------
    def locate(self, query: str, *, book_id: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        value = str(query or "").strip()
        if not value:
            raise ValueError("请说明要查的教材内容。")
        books: list[BookOutline] = []
        if book_id:
            books.append(self.index.load(book_id))
        else:
            for row in self.index.list_books():
                try:
                    books.append(self.index.load(row["book_id"]))
                except (TextbookBookNotFoundError, TextbookOutlineError):
                    continue
        hits: list[dict[str, Any]] = []
        for outline in books:
            for section, score in locate_sections(value, outline, limit=limit):
                hits.append(
                    {
                        "book_id": outline.book_id,
                        "book_title": outline.title,
                        "section_id": section.section_id,
                        "title": section.title,
                        "chapter": section.chapter,
                        "sequence": section.sequence,
                        "score": score,
                        "cached": self.cache.has(outline.book_id, section.section_id),
                    }
                )
        hits.sort(key=lambda item: (-item["score"], item["book_title"], item["sequence"]))
        return hits[: max(1, int(limit))]

    # -- L3 + L4: collect and cache -----------------------------------
    def collect_by_title(
        self, book_id: str, title: str, *, chapter: str = "", force: bool = False
    ) -> dict[str, Any]:
        """Collect a section named by the caller even before a full TOC exists."""
        section = self.ensure_section_by_title(book_id, title, chapter=chapter)
        return self.collect_section(book_id, section.section_id, force=force)

    def ensure_section_by_title(self, book_id: str, title: str, *, chapter: str = "") -> SectionRef:
        value = str(title or "").strip()
        if not value:
            raise ValueError("请提供章节标题。")
        try:
            outline = self.index.load(book_id)
        except TextbookBookNotFoundError:
            outline = BookOutline(book_id=book_id, title=book_id)
        for item in outline.sections:
            if normalize(item.title) == normalize(value):
                return item
        section = SectionRef(
            section_id=make_section_id(book_id, chapter, value),
            title=value,
            chapter=chapter,
            sequence=len(outline.sections) + 1,
        )
        self._register_section(outline, section)
        return section

    def _register_section(self, outline: BookOutline, section: SectionRef) -> BookOutline:
        if any(item.section_id == section.section_id for item in outline.sections):
            return outline
        updated = BookOutline(
            book_id=outline.book_id,
            title=outline.title,
            sections=tuple(outline.sections) + (section,),
            source=outline.source,
        )
        return self.index.save(updated)

    def collect_section(
        self,
        book_id: str,
        section_id: str,
        *,
        force: bool = False,
        progress: Callable[[dict], None] | None = None,
    ) -> dict[str, Any]:
        outline = self.index.load(book_id)
        section = outline.section(section_id)

        if not force and self.cache.has(book_id, section_id):
            record, text = self.cache.read(book_id, section_id)
            resource = self._ensure_resource(outline, section, text)
            return self._payload(outline, section, record, text, cached=True, resource=resource)

        collector = self._collector()
        result = collector.collect(outline, section, progress=progress)
        record = self.cache.write(
            book_id=book_id,
            section_id=section_id,
            title=section.title,
            path=section.path,
            text=result.text,
            screens=result.screens,
            source=result.mode,
        )
        resource = self._ensure_resource(outline, section, result.text)
        self._register_section(outline, section)
        self.retention.enforce()
        payload = self._payload(outline, section, record, result.text, cached=False, resource=resource)
        payload["screens"] = result.screens
        payload["mode"] = result.mode
        payload["anchored"] = result.anchored
        payload["stop_reason"] = result.stop_reason
        payload["duration_s"] = result.duration_s
        return payload

    def read_section(self, book_id: str, section_id: str) -> dict[str, Any]:
        outline = self.index.load(book_id)
        section = outline.section(section_id)
        record, text = self.cache.read(book_id, section_id)
        return self._payload(outline, section, record, text, cached=True, resource=None)

    def ensure_section(
        self, book_id: str, section_id: str, *, force: bool = False
    ) -> tuple[str, str]:
        """Guarantee cached text and a searchable StudyResource; returns (resource_id, text)."""
        payload = self.collect_section(book_id, section_id, force=force)
        return str(payload.get("resource_id") or ""), str(payload.get("text") or "")

    def _collector(self) -> SectionCollector:
        return SectionCollector(
            self.bridge if self.bridge is not None else AndroidBridge(),
            self.ocr if self.ocr is not None else make_default_ocr(),
            self.cache.temp_dir,
        )

    def _ensure_resource(self, outline: BookOutline, section: SectionRef, text: str):
        study = self.study
        existing = study.repository.find_resource_by_textbook_section(outline.book_id, section.section_id)
        metadata = {
            "textbook": {
                "book_id": outline.book_id,
                "book_title": outline.title,
                "section_id": section.section_id,
                "chapter": section.chapter,
                "cached_at": _now(),
            }
        }
        title = f"{outline.title} {section.title}"
        if existing is None:
            from honeyos.study.models import StudyResource

            resource = StudyResource(
                attachment_id="",
                title=title,
                resource_type="textbook",
                course_or_subject=outline.title,
                metadata=metadata,
            )
            study.repository.save_resource(resource)
        else:
            resource = existing.model_copy(
                update={"title": title, "course_or_subject": outline.title, "metadata": metadata,
                        "updated_at": datetime.now(timezone.utc)}
            )
            study.repository.save_resource(resource)
        study.library.index_resource(
            resource_id=resource.id,
            title=resource.title,
            course_or_subject=resource.course_or_subject,
            content=text,
            extraction_kind="ocr_text",
        )
        self.cache.set_resource(outline.book_id, section.section_id, resource.id)
        return resource

    def _payload(
        self,
        outline: BookOutline,
        section: SectionRef,
        record: SectionRecord,
        text: str,
        *,
        cached: bool,
        resource,
    ) -> dict[str, Any]:
        return {
            "book_id": outline.book_id,
            "book_title": outline.title,
            "section_id": section.section_id,
            "title": section.title,
            "chapter": section.chapter,
            "cached": cached,
            "text": text,
            "chars": len(text),
            "sha256": record.sha256,
            "resource_id": resource.id if resource is not None else record.resource_id,
            "stored_at": record.created_at,
        }

    # -- storage lifecycle --------------------------------------------
    def stats(self) -> dict[str, Any]:
        return {**self.retention.stats(), "books": self.list_books()}

    def cleanup(
        self, *, max_bytes: int | None = None, ttl_days: float | None = None
    ) -> dict[str, Any]:
        return self.retention.enforce(max_bytes=max_bytes, ttl_days=ttl_days)

    def purge_temp(self) -> dict[str, int]:
        return self.retention.purge_temp()

    def release_after_review(self, book_id: str, section_ids: list[str]) -> dict[str, Any]:
        from honeyos.study.review import StudyReview

        return self.retention.release_sections(
            book_id, section_ids, study=self.study, review=StudyReview(self.study)
        )
