# HoneyOS Study System — Current State

## Current Phase

Phase 2 — Study Core

Status:

    FROZEN

Phase 1 remains:

    FROZEN

Phase 0 remains:

    FROZEN

---

## Verified Development Base

Diary scheduling base commit:

    0e40294

Phase 0 implementation commit:

    b40e319a2c59b104fd417f856c95858def843718

Phase 0 freeze documentation commit:

    644bf80

Phase 1 implementation commit:

    744a7bf51d5c421ea9ea351695bdd408f7af1738


Phase 1 freeze documentation / Phase 2 baseline commit:

    103cd1056ba487991a846168491ed2af5cf45472

Phase 2 implementation commit:

    3bfb9cf471ed4e8139897bad83fa478e76626587

---

## Phase 0 — Frozen

Completed:

- canonical StudyPlan v1
- StudyTask model
- StudySession schema freeze
- StudyResource schema freeze
- canonical validation gate
- StudyPlan Markdown v1 import/export
- semantic Markdown round-trip
- isolated StudyRepository
- `~/.honeyos/study/study.db`
- StudyPlan persistence
- StudyTask persistence
- plan update/delete behaviour
- Markdown -> DB -> Markdown semantic round-trip
- Phase 0 fixtures and tests
- architecture documentation

Phase 0 canonical core lives under:

    honeyos/study/

Do not casually modify Phase 0 contracts during later phases.

---

## Phase 1 — Implementation Complete

Phase 1 establishes a generic durable HoneyOS Files / Attachment Core.

Implementation:

    honeyos/files/

Tests:

    tests/honeyos/files/

Canonical persistent root:

    ~/.honeyos/files/

Layout:

    attachments.db
    objects/sha256/...

Implemented:

- Attachment model
- upload request model
- attachment validation
- 100 MiB hard size limit
- safe display-filename handling
- canonical SHA256 object keys
- content-addressed durable storage
- atomic file publication
- duplicate-content deduplication
- SQLite attachment repository
- AttachmentService
- soft delete
- restore
- reference-safe physical deletion
- generic `/api/attachments` HTTP API
- existing API authentication reuse
- model-independent processing provider interfaces
- explicit visual-coverage semantics

---

## Phase 1 HTTP API

    POST   /api/attachments
    GET    /api/attachments
    GET    /api/attachments/{attachment_id}
    GET    /api/attachments/{attachment_id}/content
    DELETE /api/attachments/{attachment_id}
    POST   /api/attachments/{attachment_id}/restore

These routes remain outside Study, Memory, External Context, and DeepSeek-history namespaces.

---

## Verified Tests

Frozen Phase 0 Study suite:

    24 passed

Diary regression from Phase 0 closeout:

    31 passed

Files + Study combined suite:

    95 passed

Command:

    pytest -q --import-mode=importlib tests/honeyos/files tests/honeyos/study

Attachment route registration tests are also included in the Files test suite.

---

## Real Gateway Verification

Real Gateway:

    honeyos-gateway.service

Listener:

    127.0.0.1:8642

Verified end-to-end:

- local HoneyOS session cookie authentication
- attachment upload
- metadata retrieval
- list retrieval
- content download
- byte comparison
- SHA256 verification
- soft delete
- HTTP 410 for deleted content
- restore
- restored content comparison
- SQLite metadata
- physical content-addressed storage

Result:

    Attachment Core HTTP smoke test COMPLETE

Local curl tests should explicitly bypass the configured proxy:

    curl --noproxy '*'

---

## Storage Boundaries

### HoneyOS Files

Owns:

- generic file bytes
- file metadata
- hashes
- attachment lifecycle

Does not own semantic interpretation.

### Study Library

Will later own:

- StudyResource semantics
- parsing
- extracted text
- pages/slides/sections
- chunks
- source traceability
- retrieval indexes

### HoneyOS Personal Memory

Owns user-memory classification and memory cards.

Study resources and textbook facts must not become personal memory automatically.

### DeepSeek History Import

Remains a separate migration pipeline.

It may eventually use Attachment Core for raw file storage, but it does not become part of the Study Library.

### External Context

Remains a separate context store and retrieval path.

---

## Processing Architecture

Phase 1 freezes interfaces for:

- deterministic processors
- TextModelProvider
- VisionProvider
- ProcessingProviderRegistry
- ProcessingRouter

No provider-specific model dependency is introduced.

Images must never be silently ignored.

If visual material exists and no capable vision processor has handled it:

    visual_coverage = INCOMPLETE

---

## Legacy Study MVP

The existing prototype remains separate from the formal architecture:

    honeyos/companion/study.py
    frontend/src/features/study/
    ~/.honeyos/companion/study.db

It is not the canonical Study System core.

Existing dirty working-tree changes related to that prototype must not be accidentally included in the Phase 1 freeze commit.

---

## Current Known Issues

No known Phase 1 backend correctness defect remains after the real HTTP lifecycle smoke test.

Known non-blocking implementation limitation:

The current multipart HTTP bridge buffers accepted upload bytes in memory after applying the 100 MiB limit.

The lower storage layer already supports bounded streaming, so future HTTP spooling can be added without changing the core storage/service contract.

---

## Freeze Safety

The working tree contains unrelated existing changes.

In particular:

    honeyos/gateway/platforms/api_server.py

contains both Phase 1 Attachment changes and unrelated changes from other HoneyOS work.

Therefore:

DO NOT stage the entire `api_server.py` file.

Only the Attachment-specific hunks may enter the Phase 1 freeze commit.

---

## Next Actions

1. Preserve frozen Phase 0 and Phase 1 contracts.
2. Begin Phase 2 Study Core integration.
3. Reuse `attachment_id` as the Files -> StudyResource boundary.
4. Do not modify frozen Phase 1 behaviour unless a verified defect requires it.


---

## Phase 2 — Frozen

Phase 2 connects the frozen StudyPlan v1 domain to the real HoneyOS Gateway
and frontend.

Canonical chain:

    StudyPage
        -> /api/study/*
        -> StudyService
        -> StudyRepository
        -> ~/.honeyos/study/study.db

Implemented:

- StudyService application layer
- canonical Study Plan CRUD
- canonical Study Task CRUD
- explicit task-status API
- canonical frontend Study API
- Study page backed by Study Core
- /study frontend route and navigation
- persistence across Gateway restart
- strict separation from legacy companion Study persistence

Canonical API:

    GET/POST     /api/study/plans
    GET/PATCH/DELETE /api/study/plans/{plan_id}
    POST         /api/study/plans/{plan_id}/tasks
    PATCH/DELETE /api/study/plans/{plan_id}/tasks/{task_id}
    POST         /api/study/plans/{plan_id}/tasks/{task_id}/status

Verified:

    Study:                       31 passed
    Files:                       71 passed
    Combined:                   102 passed
    Python compile:             PASS
    Frontend build:             PASS
    Canonical CRUD:             PASS
    Gateway restart:            PASS
    Persistence:                PASS
    List endpoint:              PASS
    Legacy DB non-write:        PASS
    Runtime Gate:               PASS

The old Companion Study MVP remains transition-only and is not canonical.

No Study data is automatically written to HoneyOS Personal Memory,
External Context, or the DeepSeek migration pipeline.
