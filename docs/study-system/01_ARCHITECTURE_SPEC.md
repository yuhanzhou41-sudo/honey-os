# HoneyOS Study System — Architecture Specification

## 1. Domain Boundary

The production Study System lives under `honeyos/study/`.

It is independent from the temporary legacy MVP at `honeyos/companion/study.py`.

The legacy MVP may remain temporarily for UI continuity, but it is not the canonical Study architecture.

## 2. Persistent Storage

Production Study data belongs under:

    ~/.honeyos/study/

Primary database:

    ~/.honeyos/study/study.db

It must not reuse the legacy database:

    ~/.honeyos/companion/study.db

## 3. Canonical Entities

### StudyPlan

Core fields:

- id
- schema_version
- title
- description
- start_date
- end_date
- status
- focus_minutes
- break_minutes
- long_break_minutes
- long_break_after_sessions
- source_type
- goals
- timestamps

Statuses:

- draft
- active
- paused
- completed
- archived

Sources:

- honeyos_generated
- markdown_import
- manual

### StudyTask

Core fields:

- id
- plan_id
- title
- description
- scheduled_date
- planned_minutes
- status
- order_index
- review_required
- timestamps

Statuses:

- planned
- in_progress
- completed
- skipped
- deferred

### StudySession

Frozen Phase 0 schema for later runtime implementation.

Types:

- focus
- review
- quiz
- flashcard

Statuses:

- planned
- running
- paused
- completed
- abandoned

### StudyResource

Frozen Phase 0 schema for later attachment and Study Library integration.

## 4. Canonical Input Pipeline

HoneyOS-generated plan:

    HoneyOS generated data
        -> validate_study_plan()
        -> StudyPlan v1
        -> SQLite

External Markdown plan:

    Markdown
        -> Markdown parser
        -> validate_study_plan()
        -> StudyPlan v1
        -> SQLite

No plan input path may bypass canonical validation.

## 5. Markdown Interchange

StudyPlan Markdown v1 uses YAML front matter and a human-readable schedule.

Required version marker:

    study_plan_version: 1

Markdown is an interchange format. It is not the runtime source of truth.

## 6. Round-trip Requirement

The following path must preserve semantic StudyPlan data:

    Markdown
      -> StudyPlan
      -> SQLite
      -> StudyPlan
      -> Markdown
      -> StudyPlan

Runtime timestamps do not participate in semantic equality.

## 7. Legacy Study MVP

The existing Study MVP contains:

- hard-coded calendar data
- study_days
- study_tasks
- reward claims
- sunlight points
- plant growth
- temporary Study API
- temporary Study UI

These are not canonical Study domain structures.

Visual and gamification concepts may be reused later, but migration must target the new Study domain.

## 8. Integration Boundaries

Phase 0 does not modify:

- Companion chat
- Diary
- Reminder system
- Scheduler
- proactive SSE
- existing frontend
- existing Study MVP API
