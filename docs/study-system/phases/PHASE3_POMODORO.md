# Phase 3 — Pomodoro

Status:

    FROZEN

Baseline before Phase 3:

    86d3c04062ee30669936c62b213b752d08e4455e

## Scope

Phase 3 activates the frozen Phase 0 `StudySession` schema as the canonical
Pomodoro runtime.

Frozen constraints preserved:

- `StudySession` schema is unchanged.
- `StudyPlan` and `StudyTask` schemas are unchanged.
- canonical Study persistence remains `~/.honeyos/study/study.db`.
- legacy `~/.honeyos/companion/study.db` is not written.
- HoneyOS scheduler is reused; no second scheduler is introduced.
- backend timestamps are authoritative.
- frontend JavaScript countdowns are presentation only.

## Runtime architecture

```text
StudyPage
  -> frontend/src/api/study.ts
  -> /api/study/*
  -> StudyService
  -> StudySessionStore / StudyRepository
  -> ~/.honeyos/study/study.db
```

Pomodoro completion uses the existing HoneyOS scheduler:

```text
StudyService.start_session()
  -> StudyPomodoroScheduler
  -> existing cron create_job(...)
  -> one-shot + no_agent
  -> HONEYOS_HOME/scripts/study-pomodoro-<session>.sh
  -> python -m honeyos.study.pomodoro_runner complete <session_id>
  -> StudyService.complete_session(..., scheduled=True)
```

The wrapper exists because HoneyOS cron only permits relative script paths
inside `HONEYOS_HOME/scripts/`. Phase 3 does not weaken or bypass that security
boundary.

The wrapper self-deletes after successful execution. Pause, abandon, and manual
completion remove pending scheduler jobs and wrappers.

## Runtime persistence

Frozen `StudySession` fields remain stored in `study_sessions`.

Phase 3 adds internal runtime metadata in:

    study_session_runtime

Fields:

- `session_id`
- accumulated `elapsed_seconds`
- `remaining_seconds`
- `last_resumed_at`
- `scheduler_job_id`
- `updated_at`

This side table is scheduler/runtime state and does not alter the frozen
`StudySession` v1 schema.

## Lifecycle

Primary flow:

```text
planned
  -> running
  -> paused
  -> running
  -> completed
```

Terminal manual path:

```text
planned / running / paused
  -> abandoned
```

Scheduled completion records the backend-generated `expected_end_at` as the
authoritative completion time even if a scheduler tick observes it slightly
later.

## Canonical API

- `GET /api/study/plans/{plan_id}/tasks/{task_id}/sessions`
- `POST /api/study/plans/{plan_id}/tasks/{task_id}/sessions`
- `GET /api/study/sessions/{session_id}`
- `POST /api/study/sessions/{session_id}/start`
- `POST /api/study/sessions/{session_id}/pause`
- `POST /api/study/sessions/{session_id}/resume`
- `POST /api/study/sessions/{session_id}/complete`
- `POST /api/study/sessions/{session_id}/abandon`

## Frontend

`StudyPage.tsx` now uses canonical `frontend/src/api/study.ts` rather than the
transition-only Companion Study API.

Each canonical StudyTask exposes a Pomodoro control surface:

- create focus session
- start
- pause
- resume
- complete
- abandon

The visible countdown is derived from `expected_end_at` returned by the
backend. It is not authoritative state.

## Verified gates

### Unit / regression

- Phase 3 focused tests: `8 passed`
- full Study regression: `39 passed`
- Study + Files regression: `110 passed`
- standalone Files regression after one transient ordering failure: `71 passed`
- frontend TypeScript + Vite build: PASS

### Real scheduler gate

Verified against the actual HoneyOS cron implementation:

- relative wrapper script accepted
- `no_agent = true`
- scheduler execution success = true
- cron `last_status = ok`
- raw SQLite StudySession reached `completed`
- wrapper self-cleaned

### Real Gateway runtime gate

Verified through the running `honeyos-gateway.service`:

- Gateway health PASS
- local HTTP-only auth cookie PASS
- canonical StudyPlan create PASS
- canonical StudyTask create PASS
- StudySession create PASS
- start PASS
- scheduler job and wrapper creation PASS
- pause PASS
- scheduler cleanup on pause PASS
- Gateway restart PASS
- paused StudySession persisted across restart PASS
- resume PASS
- complete PASS
- canonical SQLite state PASS
- final scheduler cleanup PASS
- session list endpoint PASS
- legacy Companion Study DB hash unchanged PASS
- cascade cleanup after deleting temporary plan PASS

## Known non-Phase-3 observation

During combined regression, `tests/honeyos/files/test_repository.py::test_find_by_sha256`
failed once because two matching rows were returned in reverse order. The same
target test then passed 5/5 times, and full Files regression passed 71/71.

Because the issue did not reproduce reliably and is outside Phase 3 scope,
Phase 3 did not modify the frozen Files implementation.

## Freeze rule

Any future Pomodoro changes that alter:

- frozen StudySession fields,
- canonical Study DB location,
- scheduler reuse,
- backend-authoritative timestamps,
- or canonical `/api/study/*` runtime ownership

must be treated as an explicit architecture change rather than an incidental
Phase 3 patch.

Phase 3 implementation commit:

    2461d9deb2a2a59a47129d5b629f4f6d699bc81e

## Phase 3.2 — Classic Pomodoro

Status: FROZEN

Implementation commit:

    c6658546ccdd19ec58cfa1e5e576e08ad0b5073e

Classic defaults:

- 25 minute focus
- 5 minute short break
- 15 minute long break
- long break after 4 focus sessions

The cycle is plan-level and may continue across different StudyTasks.

Short and long breaks are first-class StudySession types and use the same
backend-authoritative timing and existing HoneyOS scheduler as focus sessions.

Real Gateway cycle gate verified:

`focus(25) -> short_break(5) -> focus(25) -> short_break(5) -> focus(25) -> short_break(5) -> focus(25) -> long_break(15) -> focus(25)`

After the long break, the plan cycle resets to 0/4.

