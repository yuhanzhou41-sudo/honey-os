# HoneyOS Study System — Phase 1: Files / Attachment Core

## Status

FROZEN

Phase 1 establishes a generic durable file and attachment layer for HoneyOS.

It is intentionally broader than the Study System and must remain independent from:

- Study Library
- HoneyOS Personal Memory
- External Context
- DeepSeek history-import and memory-migration pipelines
- Companion chat-specific media caches

The Study System consumes this layer through `attachment_id`.

---

## Goal

Provide a durable, validated, reusable attachment primitive that later HoneyOS subsystems can reference without owning raw file storage themselves.

Canonical relationship:

    HoneyOS Files / Attachment Core
        |
        | attachment_id
        v
    StudyResource
        |
        v
    Study Library

A stored attachment does not automatically become a StudyResource.

A StudyResource references an attachment.

---

## Persistent Layout

Canonical root:

    ~/.honeyos/files/

Current layout:

    ~/.honeyos/files/
    ├── attachments.db
    └── objects/
        └── sha256/
            └── <first-2>/
                └── <next-2>/
                    └── <full-sha256>

The physical object store is content-addressed by SHA256.

Original filenames are metadata only and never determine physical storage paths.

---

## Implemented Package

    honeyos/files/
    ├── __init__.py
    ├── http.py
    ├── models.py
    ├── repository.py
    ├── service.py
    ├── storage.py
    ├── validation.py
    └── processing/
        ├── __init__.py
        ├── base.py
        ├── models.py
        ├── registry.py
        ├── router.py
        └── providers/
            └── __init__.py

---

## Attachment Model

The canonical Attachment model records:

- attachment ID
- original filename
- canonical object key
- declared MIME type
- inferred MIME type
- size in bytes
- SHA256
- source type
- lifecycle status
- created timestamp
- updated timestamp

Current source types:

- upload
- chat
- study
- import

Current lifecycle statuses:

- ready
- deleted
- failed

Pydantic models use:

    extra="forbid"

Unknown fields are therefore rejected rather than silently accepted.

---

## Validation

Current maximum attachment size:

    100 MiB

Filename handling:

- strips path components
- rejects NUL/control hazards
- treats filename only as display metadata
- never uses the user filename as an object-store path

Object keys must match the canonical content-addressed shape:

    sha256/ab/cd/<full-sha256>

The validation layer does not treat filename extensions or MIME strings as security boundaries.

---

## MIME Semantics

`declared_mime_type` comes from the upload/request.

`inferred_mime_type` is currently inferred from filename/extension using Python MIME mapping.

Important:

`inferred_mime_type` is not content inspection, malware detection, magic-byte verification, or a security classification.

Future content-sniffing or file-security layers must remain separate concerns.

---

## Durable Storage

`AttachmentStorage` implements:

- content-addressed object paths
- SHA256 deduplication
- atomic temporary-file write followed by replace
- fsync before publication
- safe object-path resolution
- read-only object opening
- byte reads
- file-object streaming writes
- hard streaming size limit
- temporary-file cleanup after failure

Duplicate content may be referenced by multiple attachment metadata rows while sharing one physical object.

---

## Repository

SQLite database:

    ~/.honeyos/files/attachments.db

The repository supports:

- save/upsert
- get
- list
- find by SHA256
- soft delete
- restore
- hard delete
- total object-reference counting
- live object-reference checks

Soft-deleted metadata continues to count as a physical-object reference.

This preserves restore semantics.

---

## Service Layer

`AttachmentService` combines:

    validation
        +
    durable storage
        +
    metadata repository

It supports:

- upload bytes
- upload file object
- get attachment
- list attachments
- read attachment content
- soft delete
- restore
- hard delete

On metadata persistence failure, a newly created physical object is removed when no metadata reference remains.

Hard deletion removes the underlying physical object only when no attachment metadata row references that object.

---

## HTTP API

Generic namespace:

    /api/attachments

Implemented endpoints:

    POST   /api/attachments
    GET    /api/attachments
    GET    /api/attachments/{attachment_id}
    GET    /api/attachments/{attachment_id}/content
    DELETE /api/attachments/{attachment_id}
    POST   /api/attachments/{attachment_id}/restore

The namespace is deliberately independent from:

    /api/companion/study/*
    /api/companion/memories/*
    /api/memory/*
    /api/deepseek/*

The current multipart HTTP bridge buffers the accepted upload in memory after enforcing the configured hard size limit.

The lower storage layer itself supports bounded streaming.

A future HTTP spooling implementation may replace the in-memory bridge without changing the service or storage contracts.

---

## Authentication

The Attachment API uses the existing API server authentication mechanism.

For local HoneyOS UI sessions:

1. loopback client requests the React index
2. server sets the HTTP-only `honeyos_local` cookie
3. local API requests reuse that cookie

No separate Attachment authentication system was introduced.

---

## Delete Semantics

DELETE currently performs a soft delete.

After soft delete:

- metadata remains
- physical content remains
- restore remains possible
- content retrieval returns HTTP 410

After restore:

- status returns to `ready`
- original content becomes readable again

A public hard-delete HTTP endpoint is not part of Phase 1.

---

## Processing Provider Skeleton

Phase 1 also establishes a model-independent processing abstraction.

Capabilities:

- TEXT
- VISION

Statuses:

- COMPLETE
- PARTIAL
- FAILED
- UNAVAILABLE

Visual coverage:

- NOT_APPLICABLE
- COMPLETE
- INCOMPLETE
- UNKNOWN

Provider abstractions:

- ProcessingProvider
- TextModelProvider
- VisionProvider
- ProcessingProviderRegistry
- ProcessingRouter

No concrete text or vision model is bound during Phase 1.

In particular, Phase 1 does not integrate:

- Qwen3-4B as a Files dependency
- NeoHorse
- Cloudflare Workers AI
- TokenRhythm
- OpenSquilla

Business logic must not hard-code model names.

---

## Visual Coverage Rule

Images, diagrams, pathology images, charts, flow diagrams, arrows, spatial relationships, and visual annotations must never be silently treated as processed when only text extraction has occurred.

If visual content exists and no capable Vision Provider is available:

    visual_coverage = INCOMPLETE

The system must expose incomplete visual processing rather than silently claiming complete extraction.

This rule is required for later PDF/PPT/Word Study Library ingestion.

---

## Relationship to StudyResource

Phase 0 froze StudyResource with:

    attachment_id: str

Phase 1 supplies the durable object referenced by that field.

The intended boundary is:

    Attachment
        |
        | attachment_id
        v
    StudyResource

Phase 1 does not modify the frozen Phase 0 StudyResource schema.

---

## Relationship to Study Library

Attachment storage and Study Library are different layers.

Attachment Core owns:

- durable file bytes
- attachment metadata
- content hash
- generic lifecycle

Study Library will later own:

- parsing
- page/slide/section decomposition
- extracted text
- source locations
- chunks
- indexing
- retrieval metadata
- Study-specific resource state

A file may exist in HoneyOS Files without being imported into Study Library.

---

## Relationship to HoneyOS Memory

HoneyOS Files must not become a second personal-memory database.

Study textbook facts and source material remain Study data.

Personal Memory continues to use the existing HoneyOS memory architecture.

Study may later submit structured candidate facts/events into that existing memory pipeline when appropriate, but Attachment Core itself does not classify or create user memories.

---

## Relationship to DeepSeek History Import

The separate DeepSeek historical-conversation migration project remains outside Phase 1.

Its intended flow is:

    DeepSeek export
        |
        v
    conversation reconstruction
        |
        v
    first-level evidence
        |
        v
    candidate memories
        |
        v
    review / persistence / dedup
        |
        v
    existing HoneyOS Memory

A DeepSeek export file may eventually be stored physically through Attachment Core.

That does not make it a StudyResource.

Attachment Core stores bytes; the DeepSeek migrator owns interpretation and memory routing.

---

## Existing Media Cache

`honeyos/gateway/platforms/media_cache.py` remains a temporary/platform-media mechanism.

It is not the canonical durable HoneyOS Files store.

MIME helper ideas may be reused where appropriate, but its temporary cache semantics must not replace Attachment Core.

---

## Existing File Safety Helpers

`honeyos/agent/file_safety.py` remains defense-in-depth for local file access.

It is not an upload-admission or attachment-security subsystem.

Phase 1 therefore does not treat it as the canonical file-upload security boundary.

---

## Tests

Phase 1 includes tests for:

- attachment models
- validation
- repository
- durable storage
- service lifecycle
- HTTP handlers
- API server route registration
- namespace isolation
- processing provider registry
- processing router
- visual-coverage behaviour

Files + frozen Study Phase 0 combined suite has been verified with:

    pytest -q --import-mode=importlib tests/honeyos/files tests/honeyos/study

Result:

    95 passed

The importlib mode is required because the two test directories currently contain duplicate module basenames such as `test_models.py` and `test_repository.py`.

---

## Real Gateway Verification

The implementation has also passed a real running-gateway HTTP lifecycle test against:

    http://127.0.0.1:8642

Verified:

- local HoneyOS cookie authentication
- upload
- metadata retrieval
- list retrieval
- content download
- byte-for-byte comparison
- SHA256 equality
- soft delete
- HTTP 410 after deletion
- restore
- byte-for-byte comparison after restore
- SQLite metadata existence
- restored `ready` state
- physical content-addressed object persistence

Result:

    Attachment Core HTTP smoke test COMPLETE

The local curl test required explicit proxy bypass:

    --noproxy '*'

The Gateway itself was healthy and listening on:

    127.0.0.1:8642

---

## Phase 1 Acceptance Criteria

- [x] generic Attachment model
- [x] isolated durable Files root
- [x] SQLite attachment metadata
- [x] content-addressed SHA256 object storage
- [x] duplicate-content deduplication
- [x] hard upload size limit
- [x] filename/path safety
- [x] service lifecycle
- [x] soft delete
- [x] restore
- [x] generic HTTP namespace
- [x] API server integration
- [x] existing Study/Memory/Diary/session route boundaries preserved
- [x] model-independent processing provider interfaces
- [x] explicit visual-coverage semantics
- [x] unit/integration tests
- [x] real Gateway lifecycle smoke test
- [x] final regression after documentation closeout
- [x] Phase 1 Git commit SHA recorded
- [x] Phase 1 marked FROZEN

Phase 1 implementation commit:

    744a7bf51d5c421ea9ea351695bdd408f7af1738

Phase 1 is FROZEN.

Further changes to Phase 1 contracts require a verified defect or an explicitly scoped later-phase migration.
