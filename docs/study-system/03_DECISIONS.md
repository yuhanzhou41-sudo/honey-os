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
