from __future__ import annotations

import hashlib
import re
import unicodedata


_SPACE_RE = re.compile(r"\s+")


def normalize_memory_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = value.casefold()
    value = _SPACE_RE.sub(" ", value).strip()
    return value


def content_fingerprint(value: str) -> str:
    normalized = normalize_memory_text(value)
    return "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_subject_key(value: str) -> str:
    return normalize_memory_text(value)


def fact_fingerprint(subject: str, predicate: str, object_text: str) -> str:
    return content_fingerprint(
        "fact\n"
        + normalize_memory_text(subject)
        + "\n"
        + normalize_memory_text(predicate)
        + "\n"
        + normalize_memory_text(object_text)
    )


def procedural_fingerprint(key: str, instruction: str) -> str:
    return content_fingerprint(
        "procedural\n"
        + normalize_memory_text(key)
        + "\n"
        + normalize_memory_text(instruction)
    )
