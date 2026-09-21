# HoneyOS Study System — Phase 1 Handoff

Date:

    2026-09-21

Phase:

    Phase 1 — HoneyOS Files / Attachment Core

Status:

    IMPLEMENTATION COMPLETE — PENDING FINAL FREEZE COMMIT

---

## 1. Purpose

Phase 1 introduced a generic durable file/attachment infrastructure for HoneyOS.

This is not a Study-only file store.

It is intended to become the common durable file primitive used by Study and potentially other future HoneyOS subsystems.

---

## 2. Canonical Storage

Root:

    ~/.honeyos/files/

Database:

    ~/.honeyos/files/attachments.db

Objects:

    ~/.honeyos/files/objects/sha256/...

Physical objects are content-addressed by SHA256.

---

## 3. New Code

    honeyos/files/__init__.py
    honeyos/files/http.py
    honeyos/files/models.py
    honeyos/files/repository.py
    honeyos/files/service.py
    honeyos/files/storage.py
    honeyos/files/validation.py

Processing abstractions:

    honeyos/files/processing/__init__.py
    honeyos/files/processing/base.py
    honeyos/files/processing/models.py
    honeyos/files/processing/registry.py
    honeyos/files/processing/router.py
    honeyos/files/processing/providers/__init__.py

---

## 4. New Tests

    tests/honeyos/files/test_models.py
    tests/honeyos/files/test_validation.py
    tests/honeyos/files/test_repository.py
    tests/honeyos/files/test_storage.py
    tests/honeyos/files/test_service.py
    tests/honeyos/files/test_http.py
    tests/honeyos/files/test_api_server_routes.py

Processing tests:

    tests/honeyos/files/processing/test_registry.py
    tests/honeyos/files/processing/test_router.py

---

## 5. API Server Integration

The existing API server receives only three logical Attachment integration changes:

1. import `AttachmentHTTPHandlers`
2. initialize one generic Attachment handler rooted at `~/.honeyos/files`
3. register six generic `/api/attachments` routes

Routes:

    POST   /api/attachments
    GET    /api/attachments
    GET    /api/attachments/{attachment_id}
    GET    /api/attachments/{attachment_id}/content
    DELETE /api/attachments/{attachment_id}
    POST   /api/attachments/{attachment_id}/restore

Important:

`honeyos/gateway/platforms/api_server.py` already contains unrelated dirty changes.

Do not stage the entire file when freezing Phase 1.

---

## 6. Attachment Lifecycle

Upload:

    request
      -> validation
      -> SHA256
      -> content-addressed object storage
      -> metadata persistence
      -> ready

Soft delete:

    ready
      -> deleted

Deleted content retrieval:

    HTTP 410

Restore:

    deleted
      -> ready

Hard delete exists internally and removes physical content only after all metadata references are gone.

---

## 7. Deduplication

Two uploads with identical bytes:

- receive independent attachment metadata IDs
- share the same SHA256 object key
- share one physical object

The object is deleted only when no metadata reference remains.

---

## 8. Processing Provider Boundary

Phase 1 defines:

- ProcessingProvider
- TextModelProvider
- VisionProvider
- ProcessingProviderRegistry
- ProcessingRouter

No concrete model is integrated.

Business code must not hard-code specific model names.

---

## 9. Visual Safety Rule

Future Study document ingestion must explicitly report visual coverage.

If a page/slide contains images that have not been processed by a capable vision pipeline:

    visual_coverage = INCOMPLETE

Text extraction alone must not silently convert that state to COMPLETE.

---

## 10. Verified Tests

Files + Phase 0 Study combined suite:

    pytest -q --import-mode=importlib tests/honeyos/files tests/honeyos/study

Verified result:

    95 passed

The explicit import mode avoids pytest module-name collisions between separate test directories containing files such as `test_models.py`.

---

## 11. Real Gateway Smoke Test

Real service:

    honeyos-gateway.service

Listener:

    127.0.0.1:8642

Verified:

- GET HoneyOS index
- local `honeyos_local` authentication cookie
- POST attachment upload
- GET attachment metadata
- GET attachment list
- GET attachment content
- byte-for-byte comparison
- SHA256 comparison
- DELETE soft delete
- deleted content returns HTTP 410
- POST restore
- restored content matches original
- SQLite metadata exists
- restored status is `ready`
- physical SHA256 object exists

Final output:

    PASS: attachment metadata exists and status is ready

    Attachment Core HTTP smoke test COMPLETE

Because the development shell has HTTP proxy variables configured, local smoke tests should explicitly use:

    curl --noproxy '*'

---

## 12. Confirmed Architectural Boundaries

### Files

Generic durable raw-file storage.

### StudyResource / Study Library

Study semantics, parsing, chunks, source traceability, indexing and retrieval.

### HoneyOS Memory

User-related memories and existing memory-card lifecycle.

### External Context

Separate contextual knowledge store.

### DeepSeek History Import

Separate historical conversation evidence -> candidate memory -> existing Memory pipeline.

Do not merge these stores merely because all of them may eventually reference files or text.

---

## 13. Phase 0 Contract

Phase 0 is frozen.

StudyResource already contains:

    attachment_id

This is the intended integration point.

Phase 1 must not require changing the frozen Phase 0 schema.

---

## 14. Known Non-blocking Limitation

The current multipart HTTP bridge holds the accepted upload in memory after enforcing the configured hard size bound.

`AttachmentStorage` itself already supports bounded streaming.

A later HTTP spooling implementation can therefore improve memory behaviour without changing the core Attachment contracts.

---

## 15. Do Not Do During Freeze

Do not:

- stage all of `api_server.py`
- rewrite legacy Study MVP
- mix DeepSeek importer code into Study
- bind a concrete LLM into Attachment Core
- treat extension-derived MIME as trusted content type
- silently ignore document images
- modify frozen Phase 0 contracts without a verified defect

---

## 16. Remaining Freeze Steps

1. run final regression
2. inspect all Phase 1 diffs
3. stage `honeyos/files/`
4. stage `tests/honeyos/files/`
5. stage Phase 1 documentation
6. stage only Attachment-specific `api_server.py` hunks
7. inspect `git diff --cached`
8. create Phase 1 commit
9. record exact commit SHA
10. update status to FROZEN

---

## 17. Next Development Phase

After Phase 1 freeze:

    Phase 2 — Study Core

Phase 2 should consume frozen Phase 0 Study contracts and Phase 1 Attachment infrastructure.

Study Library parsing/indexing remains a later phase and must build on `attachment_id` rather than introducing a second raw-file store.
