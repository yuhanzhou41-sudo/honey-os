# HoneyOS Study System — Phase 2 Handoff

Date:

    2026-09-21

Status:

    PHASE 2 FROZEN

Implementation commit:

    3bfb9cf471ed4e8139897bad83fa478e76626587

Baseline entering Phase 2:

    103cd1056ba487991a846168491ed2af5cf45472

---

## Completed

Phase 2 connected the frozen canonical Study Core to the HoneyOS Gateway and
frontend.

Canonical runtime chain:

    StudyPage
        -> /api/study/*
        -> StudyService
        -> StudyRepository
        -> ~/.honeyos/study/study.db

Implemented:

- StudyService
- Study Plan CRUD
- Study Task CRUD
- task-status transitions
- canonical Study HTTP routes
- frontend Study API
- canonical StudyPage
- /study route
- Study navigation entry
- persistence across Gateway restart

---

## Verified

    Python compile:              PASS
    Study tests:                 31 passed
    Files tests:                 71 passed
    Combined tests:             102 passed
    Frontend build:              PASS

Real Gateway:

    Health:                      PASS
    Canonical plan CRUD:         PASS
    Canonical task CRUD:         PASS
    Plan status update:          PASS
    Task status update:          PASS
    Gateway restart:             PASS
    Persistence after restart:   PASS
    Plan list endpoint:          PASS
    Legacy DB non-write:         PASS
    Runtime Gate:                PASS

Local curl must bypass the configured proxy:

    curl --noproxy '*'

---

## Important Runtime Fix

Real Gateway testing identified one integration defect:

    StudyService existed but was not exported by honeyos.study

This caused:

    ImportError: cannot import name 'StudyService' from 'honeyos.study'

The public Study package now exports:

    StudyService
    StudyTaskNotFoundError

The defect was verified fixed through direct import, direct service usage,
tests, and the real HTTP endpoint.

---

## Storage Boundary

Canonical:

    ~/.honeyos/study/study.db

Legacy transition-only:

    ~/.honeyos/companion/study.db

The runtime gate compared legacy database SHA256 before and after canonical
CRUD and confirmed:

    LEGACY DB NON-WRITE PASS

---

## Do Not Merge These Systems

The following remain architecturally distinct:

    Attachment
    StudyResource
    Study Library
    HoneyOS Personal Memory
    External Context
    DeepSeek History Import

External Context source recovery and Context Ingestion development present
in the developer working tree are not part of Phase 2.

They must not be included retroactively in the Phase 2 implementation commit.

---

## Working Tree Warning

The development branch contains unrelated dirty/untracked work from:

- chat batching
- reminders/scheduler
- diary work
- Context Ingestion
- External Context recovery
- Memory UI
- DeepSeek migration integration
- generated react_dist assets
- backups and patch files

Do not use:

    git add .
    git reset --hard
    git clean -fd

Use narrow path staging or reviewed patches only.

---

## Next Phase

Phase 2 is frozen.

The next Study phase should build on the canonical API and persistence rather
than reviving the legacy Companion Study schema.

The next phase must preserve the existing boundaries unless a new documented
architecture decision explicitly changes them.
