"""Storage lifecycle for textbook material.

Rules enforced here:

* screenshots live only in ``<root>/temp`` and are purged as soon as OCR is done;
* extracted text obeys a total byte budget and an optional TTL (LRU pruned);
* once a section has been reviewed, its cached text, its StudyResource and the
  generated cards/questions/attempts can all be released together.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cache import SectionCache
from .index_store import TextbookIndexStore


@dataclass(frozen=True)
class RetentionReport:
    removed_sections: int = 0
    freed_bytes: int = 0
    temp_files: int = 0
    temp_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "removed_sections": self.removed_sections,
            "freed_bytes": self.freed_bytes,
            "temp_files": self.temp_files,
            "temp_bytes": self.temp_bytes,
        }


class TextbookRetention:
    def __init__(self, cache: SectionCache, index_store: TextbookIndexStore):
        self.cache = cache
        self.index_store = index_store

    def purge_temp(self, *, older_than_seconds: float = 0) -> dict[str, int]:
        return self.cache.purge_temp(older_than_seconds=older_than_seconds)

    def enforce(self, *, max_bytes: int | None = None, ttl_days: float | None = None) -> dict[str, Any]:
        result = self.cache.prune(max_bytes=max_bytes, ttl_days=ttl_days)
        self.index_store.cleanup_empty_dirs()
        return {**result, "temp": self.purge_temp(older_than_seconds=3600)}

    def release_sections(
        self,
        book_id: str,
        section_ids: list[str],
        *,
        study=None,
        review=None,
    ) -> dict[str, Any]:
        """Drop the derived text and, when available, its Review artifacts."""
        metas = [record for record in (self.cache.meta(book_id, item) for item in section_ids) if record]
        resource_ids = [record.resource_id for record in metas if record.resource_id]
        counts: dict[str, Any] = {"sections": 0, "resources": 0, "review": {}}
        if resource_ids and study is not None and review is not None:
            counts["review"] = review.prune_derivatives(resource_ids)
            for resource_id in resource_ids:
                try:
                    study.delete_resource(resource_id)
                except KeyError:
                    continue
                counts["resources"] += 1
        counts["sections"] = self.cache.delete_sections(book_id, section_ids)
        counts["temp"] = self.purge_temp()
        counts["stats"] = self.cache.stats()
        return counts

    def stats(self) -> dict[str, Any]:
        data = self.cache.stats()
        data["index_bytes"] = self.index_store.index_bytes()
        data.update(self.index_store.disk_usage())
        return data
