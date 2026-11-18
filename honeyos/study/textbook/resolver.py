"""Resolve a study need to a cached textbook section and its Study resource."""

from __future__ import annotations

from dataclasses import dataclass

from .service import TextbookService


class TextbookNotFoundError(KeyError):
    pass


@dataclass(frozen=True)
class ResolvedSection:
    book_id: str
    section_id: str
    title: str
    chapter: str
    resource_id: str
    text: str
    cached: bool

    @property
    def source_title(self) -> str:
        return f"{self.chapter} {self.title}".strip()


def resolve_topic(
    service: TextbookService, topic: str, *, book_id: str | None = None
) -> ResolvedSection | None:
    """Locate the best section for a topic, collecting it only when uncached."""
    hits = service.locate(topic, book_id=book_id, limit=1)
    if not hits:
        return None
    hit = hits[0]
    payload = service.collect_section(hit["book_id"], hit["section_id"])
    return ResolvedSection(
        book_id=str(hit["book_id"]),
        section_id=str(hit["section_id"]),
        title=str(hit["title"]),
        chapter=str(hit.get("chapter") or ""),
        resource_id=str(payload.get("resource_id") or ""),
        text=str(payload.get("text") or ""),
        cached=bool(payload.get("cached")),
    )


def resolve_resource_text(
    service: TextbookService, topic: str, *, book_id: str | None = None
) -> tuple[str, str, str] | None:
    """Return ``(resource_id, title, text)`` for QA/cards/questions."""
    resolved = resolve_topic(service, topic, book_id=book_id)
    if resolved is None or not resolved.resource_id:
        return None
    return resolved.resource_id, resolved.source_title, resolved.text
