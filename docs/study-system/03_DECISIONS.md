# HoneyOS Study System — Architecture Decisions

## D001 — Structured StudyPlan is canonical

Decision:

StudyPlan objects persisted in SQLite are the runtime source of truth.

Markdown is an interchange format, not the runtime source of truth.

Reason:

Runtime behaviour requires stable IDs, statuses and relationships, while Markdown should remain human-readable and editable.

Status: accepted.

---

## D002 — One validation gate

Decision:

All StudyPlan inputs must pass through:

    validate_study_plan()

This includes:

- HoneyOS-generated plans
- Markdown imports
- manually constructed plans

No input channel may bypass canonical validation.

Status: accepted.

---

## D003 — Study storage is separate

Decision:

Production Study data uses:

    ~/.honeyos/study/study.db

It does not reuse:

    ~/.honeyos/companion/study.db

Reason:

The companion database belongs to the temporary legacy Study MVP. The formal Study System needs an independent persistence boundary.

Status: accepted.

---

## D004 — Legacy Study MVP is temporary

Decision:

The current hard-coded seven-day Study MVP is not the final Study architecture.

Its UI and gamification ideas may be reused later.

Its hard-coded plan structure, study_days model and reward persistence must not become dependencies of the new Study core.

Status: accepted.

---

## D005 — Study Library is not Personal Memory

Decision:

Study materials and extracted course knowledge remain separate from:

- Personal Memory
- External Context

Reason:

Study resources are source-backed learning material, not user-profile memory.

Status: accepted.

---

## D006 — Pomodoro reuses the existing scheduler

Decision:

Do not create a second scheduling system for Study.

StudySession timing will reuse existing HoneyOS scheduling infrastructure.

Status: accepted.

---

## D007 — Server time is authoritative

Decision:

StudySession start and end timestamps are authoritative on the backend.

Frontend JavaScript timers are presentation only.

Status: accepted.

---

## D008 — Local model scope is constrained

Decision:

The local lightweight model may later perform constrained structured tasks such as:

- flashcard candidate extraction
- basic question generation
- keyword extraction
- knowledge-point extraction
- section-summary drafts
- resource classification

The local model must not be responsible for complex study planning or high-level judgment.

Status: accepted.

---

## D009 — Source traceability must be preserved

Decision:

Study resources must preserve source location wherever possible.

Examples include:

- PDF page
- PowerPoint slide
- Word heading or section
- spreadsheet sheet
- text section

Later quizzes, summaries and flashcards should be able to point back to their source material.

Status: accepted.

---

## D010 — Phase boundaries require verification

Decision:

A Study System phase is not considered frozen until:

1. implementation is complete
2. phase tests pass
3. relevant regression tests pass
4. documentation is updated
5. a handoff is written
6. the verified Git commit SHA is recorded

Status: accepted.

---

## D011 — HoneyOS Files is a generic infrastructure layer

Decision:

Durable user files are owned by a generic HoneyOS Files / Attachment Core rooted at:

    ~/.honeyos/files/

It is not owned by the Study System.

Study references generic files through `attachment_id`.

Status: accepted.

---

## D012 — Attachment is not StudyResource

Decision:

A stored Attachment and a StudyResource are different entities.

Relationship:

    Attachment
        |
        | attachment_id
        v
    StudyResource

A file can exist in HoneyOS Files without entering Study Library.

Status: accepted.

---

## D013 — Files, Study Library, Memory and External Context remain separate stores

Decision:

Do not collapse the following into one database or semantic layer:

- HoneyOS Files
- Study Library
- HoneyOS Personal Memory
- External Context

Reason:

They serve different provenance, lifecycle, retrieval and user-control requirements.

Status: accepted.

---

## D014 — DeepSeek history import remains separate from Study

Decision:

The DeepSeek historical-conversation migration project is not part of Study Library.

Its semantic pipeline remains:

    exported conversation
        -> reconstructed conversation
        -> first-level evidence
        -> candidate memory
        -> review / persistence / dedup
        -> existing HoneyOS Memory

A DeepSeek export may later use generic Attachment Core as physical storage only.

That does not make the export a StudyResource.

Status: accepted.

---

## D015 — Attachment storage is content-addressed

Decision:

Physical Attachment objects are stored by SHA256 rather than original filename.

Canonical object key:

    sha256/<2>/<2>/<full-sha256>

Reason:

This prevents user filenames from controlling storage paths and enables deterministic content deduplication.

Status: accepted.

---

## D016 — Soft delete is the public Phase 1 delete operation

Decision:

The Phase 1 HTTP DELETE operation performs a soft delete.

Soft-deleted content remains physically available for restore, but normal content retrieval returns HTTP 410.

Physical hard deletion remains an internal service/repository capability and is reference-count safe.

Status: accepted.

---

## D017 — MIME inference is not a security verdict

Decision:

`inferred_mime_type` currently represents filename/extension-based MIME inference.

It must not be treated as:

- content verification
- malware scanning
- magic-byte validation
- trust classification

Future file security/content-detection mechanisms must remain explicit.

Status: accepted.

---

## D018 — Attachment HTTP namespace is generic

Decision:

Attachment endpoints live under:

    /api/attachments/*

They must not be placed under Study, Memory, DeepSeek, or Companion-memory namespaces.

Status: accepted.

---

## D019 — Processing providers are capability-based, not model-name-based

Decision:

Business logic must depend on capabilities such as TEXT and VISION rather than concrete model names.

Phase 1 defines provider interfaces and routing only.

No specific Qwen, NeoHorse, Cloudflare, TokenRhythm, OpenSquilla, or other model is a mandatory Files dependency.

Status: accepted.

---

## D020 — Visual coverage must be explicit

Decision:

A document containing visual information must never be silently marked fully processed when only textual extraction has occurred.

If relevant images exist and no capable visual processor has handled them:

    visual_coverage = INCOMPLETE

If visual coverage cannot be established:

    visual_coverage = UNKNOWN

Reason:

PDFs, PowerPoint slides and Word documents may contain clinically or academically important information that cannot be reconstructed from OCR or text extraction alone.

Status: accepted.

---

## D021 — Local lightweight models are downstream processors

Decision:

A local text-only model must not replace deterministic file extraction or required visual processing.

Preferred future pipeline:

    Attachment
        -> deterministic extraction
        -> page/slide/section decomposition
        -> text / visual processing
        -> source-grounded content
        -> lightweight structured model processing
        -> deterministic schema/evidence validation
        -> Study Library

Status: accepted.

---

## D022 — Phase 1 maximum attachment size is 100 MiB

Decision:

The default Phase 1 attachment admission limit is:

    100 MiB

The lower storage layer enforces the limit during streaming writes.

The current HTTP multipart bridge also rejects oversized requests.

Future configuration may make the limit user- or deployment-configurable without changing the Attachment model.

Status: accepted.

---

## D023 — StudyService is the canonical Study application boundary

Decision:

Gateway and frontend canonical Study operations use:

    StudyService
        -> StudyRepository
        -> StudyPlan v1

HTTP handlers must not implement their own Study persistence logic or write
raw Study SQLite directly.

Status: accepted.

---

## D024 — Canonical Study and legacy Companion Study do not dual-write

Decision:

Canonical Study operations under:

    /api/study/*

write only to:

    ~/.honeyos/study/study.db

The transition-only legacy surface:

    /api/companion/study/*

and:

    ~/.honeyos/companion/study.db

remain separate.

Canonical CRUD must not update the legacy database.

Status: accepted.

---

## D025 — Phase 2 exposes existing frozen Study contracts rather than expanding them

Decision:

Phase 2 is an integration/application phase.

It must not use frontend requirements as a reason to casually add prototype
gamification, daily-state, memory, Study Library, or Attachment semantics to
StudyPlan v1.

Future schema changes require an explicit later-phase architecture decision
and migration strategy.

Status: accepted.
