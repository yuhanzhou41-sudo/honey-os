# Freeze — G2.2 Proactive Companion

Date: 2026-09-28

## Frozen baseline

Parent / prior freeze:

`54974605a93a9497e23554c28a36045bb0de005d`

G2.1D Momentary State is therefore a required predecessor of this phase.

## Scope

G2.2 adds a conservative companion-initiative layer on top of HoneyOS's
existing proactive companion infrastructure.

It does **not** replace the existing Topic Pool, proactive delivery,
session persistence, SSE notification, reminder, or scheduler systems.

The architecture is:

```text
Momentary State
    ↓
personal initiative eligibility
    ↓
consent / daily limit / owner idle gate
    ↓
initiative seed cooldown
    ↓
internal TopicCandidate
    ↓
existing TopicPoolStore
    ↓
existing quiet hours / minimum interval / daily delivery policy
    ↓
existing proactive event delivery
    ↓
existing durable session persistence + SSE notification
```

## Initiative policy

The initiative layer uses the companion's temporary state rather than a fixed
timer as the positive reason to speak.

Current weighted signal:

- curiosity: 0.42
- reflectiveness: 0.22
- energy: 0.18
- positive_valence: 0.14
- warmth: 0.10
- playfulness: 0.08
- tension: -0.20
- negative_valence: -0.18

Minimum initiative score:

`0.10`

Passing the threshold only makes an initiative eligible. It does not directly
send a message.

Additional gates include:

- proactive companionship must already be consented;
- daily_limit must be greater than zero;
- the owner must satisfy the configured idle window;
- an initiative seed has an additional cooldown of
  `max(6h, minimum_interval_hours)`;
- the existing Topic Pool remains authoritative for quiet hours, delivery
  frequency, reservation, and final delivery eligibility.

No extra model call is added to each ordinary user turn.

No new high-frequency polling loop is introduced.

## Topic Pool integration

Canonical persistence API:

```python
TopicPoolStore.add_candidates([candidate])
```

The internal initiative candidate uses:

- valid datetime `observed_at`;
- `expires_at = observed_at + 12h`;
- valid internal canonical HTTPS URL;
- stable generated source_id;
- category `companion`;
- score `0.8`;
- selection_reason `momentary_state_continuity`.

The 12-hour candidate expiry matches the hard expiry horizon of Momentary State
and prevents stale initiative thoughts from surviving indefinitely.

## Existing delivery infrastructure retained

G2.2 deliberately reuses the already-existing HoneyOS proactive stack:

- proactive preferences / consent controls;
- Topic Pool reservation;
- quiet hours;
- daily limit;
- minimum interval;
- proactive event construction;
- channel routing;
- durable assistant-message persistence;
- web SSE notification;
- completion / reopen semantics.

Fixed reminders remain a separate deterministic feature and are not converted
into personality-driven proactive messages.

## Regression repaired during G2.2

`tests/honeyos/test_proactive_companion_tool.py` used a fixed test timestamp
(`2026-08-09`) while the tool-created TopicPoolStore used the real wall clock.

As real time advanced, the test topic expired and `list_topics` returned an
empty list.

The test fixture now injects the same deterministic clock into the
tool-side TopicPoolStore.

Production proactive behavior was not changed for this regression.

## Validation

Final pre-freeze gate:

- corrected initiative candidate accepted by real TopicPoolStore: PASS
- focused initiative + proactive tool: 14 passed
- proactive stack / Topic Pool / gateway / web / reminder: 96 passed
- Momentary State + personality regression chain: 87 passed
- git diff --check: PASS

Behavioral invariants:

- proactive consent gate: PASS
- daily-limit gate: PASS
- owner idle gate: PASS
- Momentary-State initiative signal: PASS
- conservative no-signal => no initiative: PASS
- initiative seed cooldown: PASS
- existing Topic Pool policy remains authoritative: PASS
- existing proactive delivery path retained: PASS
- durable persistence / SSE retained: PASS
- fixed reminder contract retained: PASS
- additional per-user-turn model calls: 0
- new polling loop: NO
- Stable Core mutation: NO
- Relational Self mutation: NO
- Candidate Store mutation: NO

## Frozen files

- `honeyos/companion/proactive_initiative.py`
- `honeyos/gateway/run.py`
- `tests/honeyos/test_proactive_initiative.py`
- `tests/honeyos/test_proactive_initiative_runtime.py`
- `tests/honeyos/test_proactive_companion_tool.py`
- `docs/cognitive-memory/FREEZE_G2_2_PROACTIVE_COMPANION_2026-09-28.md`

## Next work

Future proactive work should build on this frozen seam rather than creating a
parallel delivery system. Refinements may improve proactive thought/message
quality, trigger diversity, user controls, and initiative context without
bypassing the existing Topic Pool policy and delivery contracts.
