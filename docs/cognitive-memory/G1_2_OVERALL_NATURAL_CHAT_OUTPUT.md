# G1.2 Overall Natural Chat Output

## Current design

G1.2 uses an intent-aware per-turn style mode.

### Ordinary conversation

Default:
- answer immediately,
- usually 1–3 short paragraphs,
- no automatic headings/numbering,
- no exhaustive background dump,
- no unnecessary recap/conclusion.

### Explicit structured task

When the user explicitly asks for detail, comparison, analysis, steps, modules,
tables, lists, code, debugging, documents, or similar structured work:
- preserve requested depth,
- preserve requested structure,
- do not over-compress.

## Boundary

This is expression-only guidance. It does not change retrieval, memory selection,
persistence, namespace isolation, temporal semantics, conflict resolution, or tools.

## Live-gate finding that motivated v2

The first G1.2 version improved casual small-talk but ordinary informational turns
still expanded into mini-reports. V2 therefore separates casual and structured modes
using explicit user-intent markers.
