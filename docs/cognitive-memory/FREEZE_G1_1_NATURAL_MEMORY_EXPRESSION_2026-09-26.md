# G1.1 Natural Memory Expression — Frozen 2026-09-26

## Status

PASS after live validation.

## Validated behavior

Ordinary conversation:
- relevant memory can be used naturally,
- no unsolicited retrieval-report phrasing,
- no default provenance/database/provider narration.

Explicit provenance request:
- transparent source explanation remains allowed.

## Architecture

The guard is per-turn sidecar guidance, not session-cached system-prompt guidance.

This avoids stale system-prompt cache and leaves F2 retrieval, scoring, namespace
isolation, temporal semantics, conflict resolution, and persistence unchanged.

## Non-goals

G1.1 does not guarantee memory accuracy or coverage. It only governs how remembered
context is expressed.


## 2026-11-15 implementation boundary

Per-turn wording guidance is applied only when the text turn is using
remembered context. Explicit source questions are answered to the extent
supported by the supplied evidence. Existing C1.2 chat presentation
instructions continue to handle general conversational style and requested
structure on the web surface.
