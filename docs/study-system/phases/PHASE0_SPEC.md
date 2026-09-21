# HoneyOS Study System — Phase 0

## 1. Phase Goal

Freeze the Study System domain model and interchange architecture before production integration.

The purpose of Phase 0 is to establish a stable foundation rather than modify the existing Study UI.

## 2. Existing State

Before Phase 0, HoneyOS already contained a temporary Study MVP with:

- hard-coded seven-day study data
- companion/study.db
- study_days and study_tasks tables
- reward claims
- sunlight points and plant growth
- Study frontend page
- companion Study API endpoints

This legacy MVP remains untouched during Phase 0.

## 3. Scope

Phase 0 implements:

- StudyPlan v1
- StudyTask
- StudySession schema
- StudyResource schema
- status and source enums
- canonical StudyPlan validation
- Markdown v1 parser
- Markdown v1 exporter
- semantic equality representation
- SQLite StudyRepository
- study_plans table
- study_tasks table
- reserved study_sessions table
- reserved study_resources table
- fixtures and automated tests

## 4. Out of Scope

Phase 0 does not implement:

- frontend integration
- production Study HTTP API
- migration of the legacy Study MVP
- Pomodoro execution
- attachment parsing
- Study Library search
- Study Skill
- active recall
- quizzes
- flashcards
- local LLM integration
- adaptive planning

## 5. Architecture

Canonical plan pipeline:

    Input
      -> canonical validator
      -> StudyPlan v1
      -> SQLite repository

External Markdown uses:

    Markdown
      -> Markdown parser
      -> canonical validator
      -> StudyPlan v1
      -> SQLite repository

HoneyOS-generated plans use:

    Generated structured data
      -> canonical validator
      -> StudyPlan v1
      -> SQLite repository

Both paths therefore converge before persistence.

## 6. Files

Production implementation:

    honeyos/study/
    ├── __init__.py
    ├── models.py
    ├── validation.py
    ├── markdown.py
    └── repository.py

Tests:

    tests/honeyos/study/
    ├── fixtures/
    ├── test_models.py
    ├── test_validation.py
    ├── test_markdown.py
    └── test_repository.py

## 7. Database Changes

The formal Study System uses:

    ~/.honeyos/study/study.db

Phase 0 defines:

- study_plans
- study_tasks
- study_sessions
- study_resources

Phase 0 actively persists StudyPlan and StudyTask.

StudySession and StudyResource schemas are reserved for later phases.

## 8. API

No production HTTP API changes are made in Phase 0.

The existing companion Study MVP API remains untouched.

## 9. Frontend

No frontend changes are made in Phase 0.

The existing Study MVP page remains untouched.

## 10. Implementation Steps

Completed:

1. Defined canonical Study domain models.
2. Defined stable enums and state values.
3. Added a single StudyPlan validation gate.
4. Added StudyPlan Markdown v1 parsing.
5. Added StudyPlan Markdown v1 export.
6. Added valid and invalid Markdown fixtures.
7. Added semantic round-trip verification.
8. Added isolated SQLite repository.
9. Added plan and task persistence.
10. Added Markdown -> DB -> Markdown round-trip verification.

## 11. Tests

The core Phase 0 suite reached:

    19 passed

Additional boundary tests are added during final Phase 0 closeout.

## 12. Acceptance Gate

Phase 0 is accepted only when all of the following are true:

- valid Markdown imports successfully
- invalid plans are rejected clearly
- HoneyOS-generated plans use the same validator
- unsupported schema versions are rejected
- tasks outside the plan date range are rejected
- unknown model fields are rejected
- Markdown semantic round-trip passes
- Markdown -> DB -> Markdown semantic round-trip passes
- repository uses ~/.honeyos/study/study.db
- plan updates do not leave stale tasks
- plan deletion cascades to its tasks
- boundary tests pass
- relevant HoneyOS regression tests remain acceptable
- documentation is complete
- Phase 0 receives its own verified Git commit

## 13. Regression Protection

Phase 0 must not modify:

- honeyos/companion/study.py
- existing Study frontend
- existing Study MVP gateway endpoints
- Companion chat
- Diary
- Reminder system
- Scheduler
- proactive SSE

Unrelated dirty working-tree changes must not be included in the Phase 0 commit.

## 14. Known Issues

The legacy Study MVP still exists separately.

It uses a different data model and database location.

Migration or replacement of that MVP is intentionally deferred to a later phase.

## 15. Final Result

After Phase 0, HoneyOS has a canonical Study domain layer that is independent from the temporary Study MVP.

The new architecture supports both externally imported Markdown plans and future HoneyOS-generated plans through the same validation and persistence path.

## 16. Handoff

Proceed to the next phase only after:

1. final Study tests pass
2. selected regression tests pass
3. Git diff is inspected
4. only Phase 0 files are staged
5. Phase 0 is committed
6. the commit SHA is recorded
7. CURRENT_STATE is updated
8. a Phase 0 handoff is created
9. Phase 0 is marked FROZEN
