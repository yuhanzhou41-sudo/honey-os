# Freeze — G2.3 Proactive Thought & Context

Date: 2026-09-28
Status: PASS / FROZEN after implementation and regression gates

## Parent baseline

`d4b0ec3d5e241786b694ef450c047d2afed23fec`

## Scope

G2.3 improves what Honey chooses to say when an existing proactive turn is already eligible.

It does not create a second proactive scheduler, memory retrieval pipeline,
persistence path, delivery path, or per-turn reasoning service.

## Context priority

When context is already available to the proactive turn, prefer:

1. a recent unfinished or naturally resumable conversation thread;
2. directly relevant established relationship/shared experience/remembered context;
3. established companion personality/preferences;
4. current Momentary State.

Choose one grounded conversational thread rather than enumerate all sources.

## Grounding

- use only context actually available in the turn;
- do not invent memories, shared events, preferences, unfinished topics, or urgency;
- do not create a question/task merely to force engagement;
- silence / no worthwhile proactive thought remains valid.

## User-visible expression

Do not expose retrieval/provenance labels, internal state names or scores,
scheduler/Topic Pool mechanics, or trigger/seed/selection-process narration.

## Architecture boundaries

G2.3 reuses the existing G2.2 Topic Pool and delivery pipeline.

It adds:
- no new memory retrieval pipeline;
- no new persistence path;
- no new delivery path;
- no new high-frequency loop;
- no extra model call per ordinary user turn;
- no extra model call per proactive message beyond the existing proactive generation call.

## Verification

Before freeze:
- G2.3 modules compiled;
- focused proactive-thought + G2.2 tests passed;
- broader proactive/Topic Pool/gateway/web/reminder tests passed;
- Momentary State + personality + memory-distillation tests passed;
- `git diff --check` passed.

## Next

Historical F/G/G2.x lineage remains unchanged.

Next program phase:

**C1 — Natural Conversation Runtime**
