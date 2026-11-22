"""Bounded metadata-first label lookup."""

from __future__ import annotations

import re
import unicodedata

from .u2_store import UnderstandingStore

_STOP = {"我", "的", "了", "是", "一个", "这个", "that", "the", "and"}


def terms(text: str, *, limit: int = 12) -> tuple[str, ...]:
    value = unicodedata.normalize("NFKC", text).casefold()
    found = re.findall(r"[a-z0-9][a-z0-9_-]{1,31}|[\u4e00-\u9fff]{2,12}", value)
    result: list[str] = []
    for token in found:
        pieces = [token]
        if re.fullmatch(r"[\u4e00-\u9fff]{4,12}", token):
            pieces.extend(token[i:i + 2] for i in range(len(token) - 1))
        for piece in pieces:
            if piece not in _STOP and piece not in result:
                result.append(piece)
                if len(result) == limit:
                    return tuple(result)
    return tuple(result)


def index_label(store: UnderstandingStore, label_id: str, owner: str, lane: str,
                namespace: str, text: str) -> None:
    with store.connect() as db:
        db.execute("DELETE FROM postings WHERE label_id=?", (label_id,))
        db.executemany("INSERT OR IGNORE INTO postings VALUES(?,?,?,?,?)",
                       ((term, label_id, owner, lane, namespace) for term in terms(text)))


def lookup_label_ids(store: UnderstandingStore, *, owner: str, lane: str,
                     namespace: str, query: str, per_term: int = 64,
                     total_limit: int = 768) -> tuple[tuple[str, ...], bool]:
    seen: list[str] = []
    truncated = False
    with store.connect() as db:
        for term in terms(query):
            rows = db.execute("""SELECT label_id FROM postings
                WHERE owner=? AND lane=? AND namespace=? AND term=?
                ORDER BY label_id LIMIT ?""",
                (owner, lane, namespace, term, per_term + 1)).fetchall()
            truncated |= len(rows) > per_term
            for row in rows[:per_term]:
                if row[0] not in seen:
                    seen.append(row[0])
                    if len(seen) >= total_limit:
                        return tuple(seen), True
    return tuple(seen), truncated
