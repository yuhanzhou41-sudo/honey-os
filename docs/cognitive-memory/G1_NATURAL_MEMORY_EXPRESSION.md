# G1 — Natural Memory Expression

## Goal

Prevent memory provenance leakage and retrieval-report wording during ordinary conversation while preserving transparent answers when the user explicitly asks about memory or provenance.

## Ordinary-conversation behavior

Remembered context should be used naturally as background knowledge.

Avoid unsolicited wording such as:
- "I retrieved..."
- "I found N memories..."
- "According to memory..."
- "Historical records show..."
- "I searched your memories..."

Prefer directly using the remembered fact.

## Explicit memory/provenance questions

When the user explicitly asks what Honey remembers, where information came from, how memory works, or requests an audit, Honey should answer transparently rather than pretending the information came from nowhere.

## Non-goals

G1.1 does not alter F2 retrieval, persistence, scoring, namespace isolation, time semantics, or conflict resolution.
