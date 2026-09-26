# Cognitive Memory Runtime — Phase F2 Freeze

Date: 2026-09-26

## Frozen parent

Phase F1 freeze:

`61ee4ff4fc29649ef60ec778b6c539e9256b0685`

## Phase F2 scope

Phase F2 introduced Silent Memory Context on top of the frozen F1 retrieval bridge.

Implemented stages:

- F2.1 Context Adapter
- F2.2 Shadow Context Build
- F2.3 Guarded Model Injection
- F2.4 Time / Conflict Gate
- F2.5 Natural-use Final Gate

## Runtime behavior

Cognitive Memory now follows:

user turn
→ F1 retrieval
→ SilentMemoryContext construction
→ metadata-only F2 audit
→ guarded attachment to the existing internal memory channel
→ model

The visible user message is not rewritten by F2.

## Context limits

- maximum selected memories: 3
- maximum summary chars per item: 240
- maximum memory payload chars: 700
- target total wrapper + payload: approximately 1050 chars
- external DeepSeek memories default to historical semantics

## Provenance / source behavior

The model-visible memory text does not expose:

- memory IDs
- source keys
- DeepSeek source labels
- SQL/database provenance
- retrieval scores

Provenance remains available for audit only.

## Namespace isolation

Normal/general turns do not admit roleplay/fiction memories.

Explicit roleplay turns may admit roleplay memories.

F2.5 confirmed:

- general vampire query: no Cognitive Memory RP injection
- explicit roleplay vampire query: RP memories injected as expected

Final whole-system answers may still be influenced by HoneyOS's pre-existing memory systems or conversation history. Cross-memory-system routing is outside F2 scope and should be audited separately in Phase G / unified context routing work.

## Time and conflict semantics

Current explicit user statements have higher authority than historical memory.

F2.4 adds conservative code-level suppression when all are true:

1. current turn contains explicit update/change language;
2. historical memory overlaps the same topic;
3. current and historical values conflict in the same unit/category.

Example:

- historical: 40-minute Pomodoro preference
- current: "change to 25 minutes"
- result: old 40-minute memory rejected with `current_turn_conflict`

Broad semantic contradiction guessing is intentionally disabled.

## Audit

Default audit:

`~/.honeyos/memory/runtime_context.jsonl`

F2.2 rows:
- `prompt_injection=false`
- describes the would-be context

F2.3 rows:
- `prompt_injection=true`
- written only after guarded model-context attachment

Audit is metadata-only and does not duplicate full private summaries or source keys.

## Fail-open behavior

Cognitive Memory context failures do not block the model request.

Unknown internal context types are left untouched rather than guessed/serialized.

## Validation

Before freeze:

- F2.1 focused tests: 12 passed
- F2.2 focused tests: 17 passed
- F2.3 focused tests: 23 passed
- F2.4 focused tests after value-target repair: 30 passed
- full memory suite after F2.4: 82 passed
- F2.5 audit gate: PASS
- production Cognitive Memory DB integrity: ok
- production DB counts unchanged throughout F2

## Known limitations deferred beyond F2

- F1 lexical retrieval can still return semantically weak but lexically overlapping memories.
- HoneyOS has other memory/context channels besides Cognitive Memory.
- Final assistant wording can still sound like retrieval/reporting due to existing prompts/context systems.
- Unified context-source observability is not yet implemented.
- Natural conversational style, message brevity, reactions, style-example learning, and proactive presence belong to Phase G and later.

## Freeze rule

This commit freezes the Phase F2 runtime baseline.

Future work must not casually rewrite F1/F2 behavior. Any change to retrieval, namespace boundaries, time semantics, context injection, or conflict suppression should be backed by targeted regression tests.
