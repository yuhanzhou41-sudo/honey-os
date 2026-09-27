# Freeze — G2.1C Candidate Promotion

Date: 2026-09-27
Status: PASS / FROZEN

## Purpose

Promote sufficiently mature backstage Personality Candidates into authoritative
Relational Self / Stable Core state without allowing transient behavior,
user-only preference signals, or candidate feedback loops to become permanent
personality.

## Runtime chain

```text
completed conversation
    ↓
silent observation
    ↓
periodic reflection
    ↓
Personality Candidate
    ↓
deterministic promotion maturity gate
    ↓
Relational Self
    ↓
stronger long-term maturity gate
    ↓
Stable Core
    ↓
promoted authoritative personality note
    ↓
normal runtime prompt
```

Candidates remain backstage until promoted.

## Relational Self maturity gate

Initial thresholds:

```text
support_count >= 3
confidence >= 0.65
distinct reflection batches >= 2
non-user-feedback evidence >= 2
contradiction_count < support_count
```

## Stable Core maturity gate

Stable Core is intentionally slower.

Initial thresholds:

```text
same trait already authoritative in Relational Self
support_count >= 6
confidence >= 0.75
distinct reflection batches >= 3
distinct sessions >= 3
evidence span >= 7 days
non-user-feedback evidence >= 4
contradiction_count <= 1
contradiction/support <= 0.25
```

## Anti-pleasing boundary

User feedback is evidence, not authority.

Evidence consisting only of explicit user feedback cannot promote a personality
trait.

Companion-originating/repeated self-observation evidence is required.

## Evidence provenance

Reflection now distinguishes:

```text
explicit_user_feedback only
    → user_feedback

companion-originating observed behavior
    → self_observation
```

This allows deterministic anti-pleasing promotion checks.

## Authoritative storage

Promoted personality is stored separately in:

```text
$HONEYOS_HOME/companion/personality_authority.json
```

This avoids rewriting user-authored identity/profile prose and preserves clear
auditability and rollback.

## Runtime visibility

`companion_profile_note()` now combines:

```text
existing user/profile personality context
+
promoted authoritative personality context
```

Unpromoted Candidate Store content is never added to the runtime prompt.

## Rollback / anti-resurrection

A promoted trait can be rolled back.

Rollback:
- removes the authoritative trait
- records audit/history
- blocks the same candidate_id from automatically re-promoting

Materially new future evidence may form a new candidate generation and be
evaluated independently.

## Protected identity boundary

Promotion cannot mutate reserved identity/control fields, including:

- companion_name
- assistant/display name
- user nickname
- relationship
- boundaries
- tool permissions
- safety policy
- credentials
- account identity

The HoneyOS product-name / empty companion-name invariant remains intact.

## Automatic promotion timing

A promotion scan runs after a successful personality reflection batch.

Promotion itself is deterministic and does not add another model call.

## Failure behavior

Promotion/runtime-note failures are fail-open.

They do not block the user-visible conversation.

## Not included

Momentary State remains outside G2.1C.

No dedicated idle polling loop is introduced.

## Verification

G2.1C promotion + personality chain:

```text
48 passed
```

Profile + distillation regression:

```text
31 passed
```

Total relevant:

```text
79 passed
```

`git diff --check` passed.

## Result

HoneyOS can now:

```text
observe itself
→ periodically reflect
→ form candidates
→ deterministically mature candidates
→ promote mature traits
→ expose only promoted traits to normal runtime
```

This is the first complete end-to-end persistent personality formation path.
