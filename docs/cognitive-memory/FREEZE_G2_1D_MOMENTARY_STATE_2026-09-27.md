# Freeze — G2.1D Momentary State

Date: 2026-09-27
Status: PASS / FROZEN

## Purpose

Add a short-lived companion state layer below Stable Core and Relational Self.

Momentary State is temporary context, not durable personality and not a
proactive-message trigger.

## Architecture

```text
Stable Core
    ↓
Relational Self
    ↓
Momentary State
    ↓
normal response
```

## State axes

Initial axes:

- curiosity
- reflectiveness
- seriousness
- warmth
- energy
- playfulness
- tension
- positive valence
- negative valence

## Source boundary

Momentary State is updated only from explicit signals in the companion's own
completed response.

It does not infer the user's emotional state.

## Runtime timing

State update runs only after a completed, non-interrupted turn whose session
persistence did not fail.

State update occurs before the existing personality observation hook.

## Cost

Momentary State is deterministic and model-free.

```text
additional model calls per turn = 0
```

## Decay

Initial decay policy:

```text
half-life = 3 hours
hard idle expiry = 12 hours
```

After long inactivity, temporary state returns to neutral.

## Runtime visibility

Only sufficiently active temporary state is added to runtime personality
context.

The model receives a compact instruction to let the state subtly color tone
and initiative without mechanically announcing or explaining the internal
state.

## Separation from persistent personality

Momentary State does not:

- create Personality Candidates
- strengthen or contradict candidates
- promote Relational Self
- promote Stable Core
- update personality authority
- mutate companion_name

## Proactive messaging

G2.1D does not itself initiate messages.

Momentary State is intentionally usable as an input to the next system:

```text
G2.2 Proactive Companion
```

For example, curiosity or positive energy may later influence whether and how
the companion initiates a message, but the trigger policy belongs to G2.2.

## Verification

Momentary State + personality-chain tests:

```text
56 passed
```

Profile + memory-distillation regression:

```text
31 passed
```

Total relevant verification:

```text
87 passed
```

`git diff --check` passed.

## Result

The three-layer personality model is now operational:

```text
Stable Core
+
Relational Self
+
Momentary State
```

Persistent personality and temporary state remain explicitly separated.

## Next phase

G2.2 — Proactive Companion / proactive messaging.

The next phase should implement initiative policy, trigger sources,
anti-spam/cooldown behavior, context assembly, delivery, persistence, and
user-control boundaries while reusing existing HoneyOS scheduler and
proactive-message infrastructure where possible.
