# Freeze — Cognitive Memory Runtime Phase F1

Date: 2026-09-26

## Baseline

- Parent commit: `d83acf37c39a9aec33f995594a4f2c86246fb1bf`
- Branch: `feature/chat-message-batching`

## Scope

Phase F1 is a **shadow-only runtime retrieval bridge**.

Implemented:

- `honeyos/memory/runtime_shadow.py`
  - read-only retrieval over active external Cognitive Memory episodes
  - source tombstone exclusion
  - deterministic lexical scoring
  - query-scaffolding removal for retrieval scoring
  - runtime namespace classifier independent from UI presentation partitions
  - roleplay / fiction namespace gate
  - max 3 selected candidates
  - total selected preview budget <= 900 characters
  - JSONL audit at `~/.honeyos/memory/runtime_shadow.jsonl`
- `honeyos/agent/turn_context.py`
  - fail-open shadow hook in the turn prologue
  - shadow results are **not** assigned to `ext_prefetch_cache`
  - shadow results are **not** appended to `api_content`
  - shadow results are **not** added to the system prompt
  - shadow results are **not** exposed in `TurnContext`
- `tests/honeyos/memory/test_runtime_shadow.py`
  - tombstone exclusion
  - roleplay / fiction namespace boundaries
  - result count and character budget
  - audit semantics
  - query-scaffolding removal
  - short-subject handling
  - generic Chinese collision reduction
  - HoneyOS entity-priority regression
  - fiction structural-cue regression

## Runtime contract

- Prompt injection: **disabled**
- User-visible response behavior: **unchanged by Cognitive Memory F1**
- Cognitive Memory database writes from F1 retrieval: **none**
- Current user turn remains authoritative.
- Provenance/source identity remains internal audit data.
- UI history partitions are presentation heuristics only and are not trusted as the runtime namespace boundary.

## Validation

Latest code validation before freeze:

- Cognitive Memory / F1 tests: `52 passed`
- Agent tests: `3 passed`
- Production DB integrity: `ok`
- Production DB counts unchanged during tests:
  - episodes: 1984
  - provenance: 7607
  - tombstones: 1
  - feedback: 0
  - facts: 0
  - edges: 0
  - salience: 0

## Live shadow gate

Verified against production history with these classes of queries:

- HoneyOS project status
  - selected relevant HoneyOS project memory
  - generic “system” collisions removed
- childhood / family context
  - selected real personal-history memories
  - fiction / roleplay candidates rejected by namespace guard
- explicit roleplay vampire retrieval
  - selected relevant roleplay memories
- general vampire query
  - roleplay candidates rejected by namespace guard

Every inspected live row had:

- `prompt_injection=false`
- selected count <= 3
- selected preview character budget <= 900

## Isolation

`honeyos/agent/turn_context.py` already had unrelated dirty work before Phase F1.
The freeze reconstructs its staged version as:

`HEAD + (pre-F1 turn_context baseline -> current turn_context)`

using the exact pre-F1 backup:

`/mnt/d/HoneyOS-Transfer/memory-phase-f1-backups/20260926-144251/honeyos/agent/turn_context.py`

This preserves unrelated working-tree changes while committing only the F1 delta.

## Explicitly not included

- F2 memory prompt injection
- semantic embeddings / vector search
- LLM reranking
- native HoneyOS/Cognitive Memory conflict merging
- semantic consolidation into facts/edges/salience
- companion response-style changes

## Reopen criteria

Reopen F1 only for a verified defect in:

- shadow hook execution
- tombstone exclusion
- namespace leakage
- retrieval scoring regression
- audit logging
- result or character-budget enforcement
