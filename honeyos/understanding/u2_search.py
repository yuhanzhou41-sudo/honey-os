"""Bounded metadata-first label lookup."""

from __future__ import annotations

import re
import unicodedata

from .u2_store import UnderstandingStore

_STOP = {"我", "的", "了", "是", "一个", "这个", "that", "the", "and"}

# CJK runs are matched whole (not in fixed 12-char windows) so two-character
# words that straddle a window boundary (e.g. 娃娃 at the end of a clause)
# still produce an indexable term.
_WORD = re.compile(r"[a-z0-9][a-z0-9_-]{1,31}|[\u4e00-\u9fff]+")


def terms(text: str, *, limit: int = 12) -> tuple[str, ...]:
    value = unicodedata.normalize("NFKC", text).casefold()
    result: list[str] = []
    for token in _WORD.findall(value):
        if token[0].isascii():
            pieces = [token]
        else:
            pieces = [token[i:i + 2] for i in range(len(token) - 1)]
            if len(token) <= 12:
                pieces.insert(0, token)
        for piece in pieces:
            if piece not in _STOP and piece not in result:
                result.append(piece)
                if len(result) == limit:
                    return tuple(result)
    return tuple(result)


def index_label(store: UnderstandingStore, label_id: str, owner: str, lane: str,
                namespace: str, text: str) -> None:
    # Index the whole label text, not just its first 12 terms: the canonical
    # key prefix alone used to consume the budget, hiding the meaningful words
    # of the understanding body from topic lookup.
    with store.connect() as db:
        db.execute("DELETE FROM postings WHERE label_id=?", (label_id,))
        db.executemany("INSERT OR IGNORE INTO postings VALUES(?,?,?,?,?)",
                       ((term, label_id, owner, lane, namespace)
                        for term in terms(text, limit=48)))


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
