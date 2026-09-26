# Freeze — G2.1B.1 Personality Candidate Store

Date: 2026-09-26
Status: PASS / FROZEN

## Purpose

Provide a provisional, non-authoritative persistence layer for emerging companion-personality traits.

G2.1B.1 records candidate traits, supporting evidence, contradictory evidence, rejection/suppression, and audit history.

It does not alter the live companion personality.

## Files

- `honeyos/companion/personality_candidates.py`
- `tests/honeyos/test_personality_candidates.py`

## Storage contract

Runtime store location:

```text
$HONEYOS_HOME/companion/personality_candidates.sqlite
```

Audit trail:

```text
$HONEYOS_HOME/companion/personality_candidate_audit.jsonl
```

Tables:

- `personality_candidates`
- `personality_candidate_evidence`
- `personality_candidate_suppressions`

## Supported operations

- create candidate
- aggregate repeated support
- add evidence
- record contradiction
- list/get candidates
- list evidence
- reject candidate
- suppress candidate
- anti-resurrection for rejected/suppressed evidence

## Anti-resurrection semantics

Same evidence after rejection is blocked.

Materially different later evidence may form a new candidate generation for the same trait key.

Historical rejected/suppressed candidates remain auditable.

Only one active candidate for a `(target_layer, trait_key)` may exist at a time.

## Personality boundaries

Allowed target layers:

- `relational_self`
- `stable_core`

Momentary state is not persisted directly as a personality candidate.

## Name invariant

Automatic personality formation has no authority over companion naming.

The Candidate Store:

- has no `companion_name` column
- rejects `name`
- rejects `companion_name`
- rejects identity payload fields
- never mutates `IDENTITY.md` naming state

G2.1A.1 remains authoritative:

```text
product identity = HoneyOS
companion personal name = optional / empty until explicitly assigned
```

## Persistence isolation

G2.1B.1 does not write:

- `IDENTITY.md`
- `RELATIONSHIP.md`
- `SOUL.md`
- cognitive memory
- tool permissions
- safety policy

## Runtime boundary

Not implemented in G2.1B.1:

- runtime observation hook
- automatic personality extraction
- periodic reflection
- candidate promotion
- automatic `IDENTITY.md` update
- prompt injection of candidate state

## Verification

Focused Candidate Store tests:

```text
10 passed
```

Profile + distillation regression:

```text
31 passed
```

Total relevant verification:

```text
41 passed
```

## Next phase

G2.1B.2 — Candidate Observation Hook

The observation phase must remain silent to the user and should avoid one-model-call-per-turn architecture.

Recommended direction:

```text
ordinary conversation
    ↓
cheap observation capture
    ↓
pending observation buffer
    ↓
periodic / threshold-triggered personality reflection
    ↓
Personality Candidate Store
```

No personality reasoning should be inserted into the visible assistant response.
