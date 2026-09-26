# Freeze — G2.1B.2b Periodic Personality Reflection Runner

Date: 2026-09-26
Status: PASS / FROZEN

## Purpose

Provide a low-frequency, batch-oriented, silent personality reflection runner.

The runner consumes pending observations through an injected adapter and applies
strictly validated Candidate Store operations.

## Trigger policy

Default policy:

```text
pending >= 20
OR
oldest pending >= 24h AND pending >= 5
```

Automatic reflection is rate limited to:

```text
<= 1 successful automatic reflection / 12h
```

Normal conversation adds:

```text
0 extra reflection model calls
```

## Adapter boundary

The runner accepts an injected adapter.

G2.1B.2b does not connect:

- a real model
- scheduler
- chat runtime
- prompt assembly

## Structured reflection

Allowed actions:

- `create`
- `support`
- `contradict`
- `none`

All operations must pass strict validation before mutation.

Reserved identity fields and name-related trait keys remain rejected.

## Atomicity

The runner performs:

1. JSON/schema validation
2. evidence-id validation
3. business dependency preflight
4. Candidate Store mutation
5. observation processing mark

Business dependency failure is detected before any mutation.

A later invalid operation cannot leave an earlier operation persisted.

On failure:

```text
Candidate Store mutation: none
pending observations: retained
normal chat: unaffected
```

## Failure behavior

Failures are fail-open with respect to conversation.

Reflection state records:

- last attempt
- last success
- last batch
- last observation count
- last error

## Hidden reasoning boundary

The runner never emits user-facing personality-analysis prose.

It operates on bounded observation excerpts and structured data only.

No hidden chain-of-thought is stored or exposed.

## No promotion

This phase does not modify:

- `IDENTITY.md`
- `RELATIONSHIP.md`
- `SOUL.md`

Candidate state is backstage and is not injected into the normal conversation prompt.

## Name invariant

No `companion_name` mutation path is added.

Automatic personality reflection remains outside naming authority.

## Verification

Reflection Runner focused tests:

```text
11 passed
```

Candidate/Profile/Distillation regression:

```text
46 passed
```

Total relevant verification:

```text
57 passed
```

## Next phase

G2.1B.2c — Runtime Hook

The runtime phase should connect completed assistant turns to observation capture
without adding a per-turn large-model reflection call.
