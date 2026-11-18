"""On-demand textbook collection (index -> locate -> collect -> cache -> clean)."""

from .android_bridge import AdbError, AndroidBridge, MuMuManager, default_adb_path, default_serial
from .cache import SectionCache, SectionRecord, TextbookCacheError
from .collector import CollectResult, SectionCollector, TextbookCollectionError, TextbookNavigationError
from .index_store import TextbookBookNotFoundError, TextbookIndexError, TextbookIndexStore
from .ocr import OcrUnavailable, TesseractOcr, VisionOcr, make_default_ocr
from .outline import (
    BookOutline,
    SectionRef,
    TextbookOutlineError,
    locate_sections,
    parse_outline_from_text,
    parse_outline_from_ui_dump,
    parse_toc_from_ui_dump,
    score_section,
)
from .retention import TextbookRetention
from .service import TextbookService, TextbookServiceError, default_textbook_root

__all__ = [
    "AdbError",
    "AndroidBridge",
    "BookOutline",
    "CollectResult",
    "MuMuManager",
    "OcrUnavailable",
    "SectionCache",
    "SectionCollector",
    "SectionRecord",
    "SectionRef",
    "TesseractOcr",
    "TextbookBookNotFoundError",
    "TextbookCacheError",
    "TextbookCollectionError",
    "TextbookIndexError",
    "TextbookIndexStore",
    "TextbookNavigationError",
    "TextbookOutlineError",
    "TextbookRetention",
    "TextbookService",
    "TextbookServiceError",
    "VisionOcr",
    "default_adb_path",
    "default_serial",
    "default_textbook_root",
    "locate_sections",
    "make_default_ocr",
    "parse_outline_from_text",
    "parse_outline_from_ui_dump",
    "parse_toc_from_ui_dump",
    "score_section",
]
