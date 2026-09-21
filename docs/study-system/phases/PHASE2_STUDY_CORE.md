# Phase 2 — Study Core

Status:

    FROZEN

Implementation commit:

    3bfb9cf471ed4e8139897bad83fa478e76626587

Phase 2 connects the frozen Phase 0 StudyPlan v1 domain to the HoneyOS
Gateway and frontend without changing the frozen Phase 0 schema.

---

## Canonical Architecture

    StudyPage
        -> /api/study/*
        -> StudyService
        -> StudyRepository
        -> ~/.honeyos/study/study.db

Canonical persistence:

    ~/.honeyos/study/study.db

Legacy prototype persistence remains separate:

    ~/.honeyos/companion/study.db

There is no canonical/legacy dual-write path.

---

## Phase 2 Implementation

Application layer:

    honeyos/study/service.py

Public Study package exports:

    StudyService
    StudyTaskNotFoundError

Frontend canonical API:

    frontend/src/api/study.ts

Frontend Study page:

    frontend/src/features/study/StudyPage.tsx

Gateway integration:

    honeyos/gateway/platforms/api_server.py

Frontend routing/navigation:

    frontend/src/app/App.tsx
    frontend/src/app/AppShell.tsx

Tests:

    tests/honeyos/study/test_service.py
    tests/honeyos/study/test_api_server_routes.py

---

## Canonical HTTP API

    GET    /api/study/plans
    POST   /api/study/plans

    GET    /api/study/plans/{plan_id}
    PATCH  /api/study/plans/{plan_id}
    DELETE /api/study/plans/{plan_id}

    POST   /api/study/plans/{plan_id}/tasks

    PATCH  /api/study/plans/{plan_id}/tasks/{task_id}
    DELETE /api/study/plans/{plan_id}/tasks/{task_id}

    POST   /api/study/plans/{plan_id}/tasks/{task_id}/status

SPA route:

    GET /study

---

## Frozen Behaviour

Phase 2 supports:

- list plans
- create plan
- read plan
- update plan
- delete plan
- create task
- update task
- delete task
- explicit task-status transition
- canonical frontend plan/task rendering
- frontend plan creation and selection
- frontend plan deletion
- frontend task creation and deletion
- frontend task-status updates
- persistence through Gateway restart

New manual Study Plans are created with:

    source_type = manual

Clients cannot forge imported/generated provenance through the manual CRUD API.

New Study Tasks begin in the canonical planned state.

Updates are validated through the frozen Phase 0 StudyPlan v1 validation gate.

---

## Architecture Boundaries

Phase 2 does not merge:

    Attachment
    StudyResource
    Study Library
    HoneyOS Personal Memory
    External Context
    DeepSeek History Import

Attachments remain generic Phase 1 Attachment objects.

Study Library parsing is not implemented in Phase 2.

Study information is not automatically persisted to HoneyOS Personal Memory.

External Context remains an independent retrieval system.

DeepSeek historical conversation migration remains an independent pipeline.

---

## Legacy Study MVP

The earlier prototype remains transition-only:

    honeyos/companion/study.py
    ~/.honeyos/companion/study.db
    /api/companion/study/*

Its fields such as:

- sunlight
- plant state
- rewards
- minimum mode
- seven-day hard-coded schedule
- prototype daily metrics

are not part of canonical StudyPlan v1.

Phase 2 does not dual-write canonical operations into the legacy database.

---

## Verification

### Python compile

Result:

    PASS

### Study test suite

Result:

    31 passed

### HoneyOS Files regression suite

Result:

    71 passed

### Combined Study + Files regression

Command:

    pytest -q --import-mode=importlib tests/honeyos/study tests/honeyos/files

Result:

    102 passed

The importlib mode is required because the Study and Files test directories
contain several same-named test modules.

### Frontend build

Result:

    PASS

Vite completed successfully.

The existing large-chunk warning is not a Phase 2 correctness failure.

---

## Real Gateway Runtime Gate

Gateway:

    honeyos-gateway.service

Listener:

    127.0.0.1:8642

Local HTTP verification bypassed the configured proxy:

    curl --noproxy '*'

Runtime verification performed:

1. Gateway health check.
2. Create canonical Study Plan.
3. Create canonical Study Task.
4. Update Study Task.
5. Change Study Task to completed.
6. Change Study Plan to active.
7. Confirm canonical SQLite database exists.
8. Restart Gateway.
9. Re-read the Study Plan after restart.
10. Verify all Plan/Task state persisted.
11. Verify list endpoint contains the Plan.
12. Compare legacy Study database SHA256 before and after.

Result:

    COMBINED REGRESSION PASS
    CANONICAL DB PASS
    PERSISTENCE PASS
    LIST ENDPOINT PASS
    LEGACY DB NON-WRITE PASS
    PHASE 2 RUNTIME GATE PASS

Runtime test objects were subsequently removed through the canonical API.

The canonical database itself remains:

    ~/.honeyos/study/study.db

---

## Phase 2 Runtime Defect Found and Fixed

During real Gateway verification, the canonical endpoint initially returned
HTTP 500 because StudyService was implemented but not exported by:

    honeyos/study/__init__.py

The package export was corrected and StudyService and
StudyTaskNotFoundError are now part of the public Study package API.

A diagnostic call also demonstrated that StudyService accepts a
StudyRepository instance, not a HoneyOS-home Path. The canonical default
constructor remains:

    StudyService()

which creates the frozen StudyRepository through its normal default path.

After the export correction:

    import contract PASS
    direct StudyService PASS
    Gateway /api/study/plans PASS

---

## Freeze Rule

Phase 2 is now frozen.

Later phases must not casually change:

- StudyPlan v1 schema
- StudyTask schema
- canonical StudyRepository persistence
- canonical /api/study/* semantics
- canonical-vs-legacy database boundary

A future change to these contracts requires an explicit migration or
documented architecture decision rather than an incidental frontend or
feature patch.
