"""Recover a recent self-authored, unfinished intention from active dialogue."""
from __future__ import annotations

import json
import re
import time

from honeyos.companion.affect_evidence import assistant_self_clauses
from honeyos.memory.runtime_shadow import _query_terms

_DEFERRED = re.compile(
    r"^我(?:自己)?(?:还|也)?(?:想|希望)(?:稍后|之后|下次|改天|接下来|继续)\s*(.+)"
    r"|^I (?:still )?(?:want|would like) to (?:continue|revisit|return to|come back to)\s+(.+)",
    re.I,
)
_DECLINED = re.compile(r"别再|不用继续|不想继续|不聊这个|到此为止|\b(?:drop it|stop|leave it|move on)\b", re.I)
_FOLLOW_UP = re.compile(r"^(?:继续(?:聊吧|说吧)?|接着说|你(?:还|刚才)想说什么|go on|please continue)[。！.!\s]*$", re.I)


def pending_intention_context(db, session_id: str, query: str, *, now: float | None = None) -> str:
    if _DECLINED.search(query):
        return ""
    latest = db.latest_message_row_id(session_id, role="assistant")
    if latest is None:
        return ""
    window = db.get_messages_around(session_id, latest, window=8)["window"]
    cutoff = (time.time() if now is None else now) - 48 * 3600
    terms = _query_terms(query)
    for row in reversed(window):
        value = row.get("content")
        if not row["active"] or not isinstance(value, str) or not isinstance(row.get("timestamp"), (int, float)):
            continue
        if row["timestamp"] < cutoff:
            break
        if row["role"] == "user" and _DECLINED.search(value):
            break
        if row["role"] != "assistant" or row.get("tool_calls") or row.get("display_kind") in {"hidden", "auto_continue"}:
            continue
        for clause in assistant_self_clauses(value[:1000]):
            match = _DEFERRED.match(clause)
            if match is None:
                continue
            topic = next(group for group in match.groups() if group)
            related = sum(weight for term, weight in terms if term in topic.casefold()) >= 3
            if related or (_FOLLOW_UP.fullmatch(query.strip()) and row["id"] == latest):
                return (
                    "[Honey's recent optional intention, from its own earlier reply. "
                    "Use only if it still fits the exchange.] "
                    + json.dumps(clause[:150], ensure_ascii=False)
                )
        # An intervening assistant reply that already addresses the topic
        # consumes the earlier intention for this follow-up.
        if sum(weight for term, weight in terms if term in value[:1000].casefold()) >= 3:
            break
    return ""
