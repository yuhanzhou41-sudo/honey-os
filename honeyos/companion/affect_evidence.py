"""Conservative ownership boundaries for companion self-appraisal evidence."""
from __future__ import annotations

import re

_CITATION = re.compile(
    r'```[\s\S]*?(?:```|$)|`[^`\n]*`|(?m:^\s*>[^\n]*)|'
    r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"|‘[^’]*’',
)
_CLAUSES = re.compile(r"([。！？!?;；\n]+|(?<!\d)\.(?=\s|$)|[，,]\s*(?=(?:但|不过|but\s+)))", re.I)
_REPORTED = re.compile(
    r"^(?:你|用户|他|她|角色).{0,24}(?:说|写|表示|提到|觉得|感到)|"
    r"^(?:you|the user|he|she|the character)\b.{0,40}\b(?:said|wrote|feel|felt|told|reported)\b",
    re.I,
)
_SELF = re.compile(
    r"^(?:但(?:是)?|不过|其实|至于我[，,:：]\s*)?\s*"
    r"(?:我(?=自己|的|对|也|有点|很|挺|不|担心|挂念|希望|想|在意|好奇|觉得|感到|意识到|发现|没|终于|愿意)"
    r"|(?:I|my)\b|(?:but|however|personally|for me)[,:]?\s+(?:I|my)\b)",
    re.I,
)
_ABOUT_SOMEONE_ELSE = re.compile(
    r"^(?:(?:但(?:是)?|不过|其实)[，,]?\s*)?"
    r"(?:我(?:知道|理解|能理解|看得出|看得出来|听得出|认为|觉得|担心)\s*(?:你|用户|他|她)"
    r"|(?:(?:but|however)[,:]?\s+)?I\s+(?:know|understand|see|can see|think|feel|worry)\s+"
    r"(?:that\s+)?(?:you|he|she|the user)\b)",
    re.I,
)


def assistant_self_clauses(reply: str) -> tuple[str, ...]:
    """Find direct first-person clauses outside quotations and reported speech."""
    cleaned = _CITATION.sub(" ", reply or "")
    # Keep normal punctuation so evidence validation can use exact source spans.
    parts = _CLAUSES.split(cleaned) + [""]
    evidence = []
    for body, separator in zip(parts[::2], parts[1::2]):
        clause = (body + separator).strip()
        if _SELF.search(clause) and not (_REPORTED.search(clause) or _ABOUT_SOMEONE_ELSE.search(clause)):
            evidence.append(clause)
    return tuple(evidence)
