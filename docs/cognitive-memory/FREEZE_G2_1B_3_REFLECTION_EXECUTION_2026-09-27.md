# Freeze — G2.1B.3 Reflection Execution Integration

Date: 2026-09-27
Status: PASS / FROZEN

## Purpose

Connect the frozen personality observation and reflection infrastructure to a
real HoneyOS auxiliary-model execution path while preserving zero per-turn
reflection calls below threshold.

## Runtime flow

```text
completed assistant turn
    ↓
silent observation capture
    ↓
cheap should_reflect() check
    ↓
threshold false → stop, 0 model calls
    ↓
threshold true
    ↓
background reflection thread
    ↓
cross-thread/process reflection lock
    ↓
HoneyOS auxiliary_client call
    ↓
strict runner validation/apply
    ↓
Candidate Store
```

## Real model adapter

The implementation reuses HoneyOS auxiliary-model infrastructure.

It does not create a new provider stack.

The adapter:
- uses `honeyos.agent.auxiliary_client.call_llm`
- carries configured main-runtime routing when available
- sends bounded observations only
- requests JSON-only personality reflection output
- records model/provider/token metadata when available

## Trigger policy

Frozen B.2b policy remains:

```text
pending >= 20
OR
pending >= 5 AND oldest pending >= 24h
```

Successful automatic reflection remains rate-limited.

When threshold is false:

```text
model calls = 0
background thread creation = 0
```

## Concurrency

Reflection execution uses:
- in-process thread lock
- best-effort cross-process file lock

The policy is re-checked after lock acquisition to avoid duplicate reflection
of already-consumed pending observations.

## Failure behavior

If the model call, parsing, validation, or application fails:

```text
normal chat: unaffected
pending observations: retained
candidate mutation: none
```

## Prompt isolation

The reflection prompt receives bounded observation batches only.

It does NOT receive:
- active Candidate Store content
- authoritative personality files
- hidden chain-of-thought
- conversation UI callbacks

This preserves the no-self-reinforcement boundary.

## Cost/audit

When available, audit records:
- provider
- model
- prompt tokens
- completion tokens
- total tokens
- reflection batch id

## Runtime guarantees

G2.1B.3 does NOT:
- add a model call to ordinary turns below threshold
- modify visible assistant output
- inject reflection output into conversation history
- promote candidates
- update `IDENTITY.md`
- update `RELATIONSHIP.md`
- update `SOUL.md`
- mutate `companion_name`

## Idle-age limitation

No dedicated polling loop was added.

The 24h age trigger is evaluated on later eligible activity.
A fully idle HoneyOS instance does not wake solely to run personality reflection.

This is an accepted limitation for G2.1B.3.

## Verification

Reflection execution / observation / reflection / candidate chain:

```text
44 passed
```

Profile + distillation regression:

```text
31 passed
```

Total relevant:

```text
75 passed
```

`git diff --check` passed.

## Next phase

G2.1C — Candidate Promotion

The next phase should define and implement controlled promotion from backstage
Personality Candidates into authoritative Relational Self / Stable Core state,
with maturity thresholds, contradiction handling, rollback/audit, and no name
or identity-authority leakage.
