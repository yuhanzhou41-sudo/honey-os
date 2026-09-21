# HoneyOS Study System — Master Roadmap

## Goal

Build a general-purpose HoneyOS Study System supporting:

- reusable study plans
- Markdown import/export
- study sessions and Pomodoro
- study resources and library
- HoneyOS Study Skill
- active recall and quizzes
- flashcards
- local lightweight LLM extraction
- later adaptive planning

## Core Architecture Rule

Study runtime data uses canonical structured models and SQLite.

Markdown is an interchange format, not the runtime source of truth.

Both HoneyOS-generated plans and externally imported Markdown plans must pass through the same canonical StudyPlan validator.

## Phase Roadmap

### Phase 0 — Specification Freeze
Status: implementation complete, pending final regression and commit.

Scope:

- StudyPlan v1 schema
- StudyTask schema
- StudySession schema freeze
- StudyResource schema freeze
- Markdown v1 import/export
- unified validation gate
- SQLite repository
- semantic round-trip tests

### Phase 1 — General Attachments

Support shared HoneyOS attachment infrastructure for:

- PDF
- DOCX
- PPTX
- XLSX
- CSV
- TXT
- Markdown
- images

Preserve source structure and traceability.

### Phase 2 — Study Core

Implement production Study UI and API using:

- study_plans
- study_tasks
- study_sessions
- study_resources

Replace hard-coded Study MVP data source.

### Phase 3 — Pomodoro

Reuse HoneyOS scheduler.

Server timestamps are authoritative.

### Phase 4 — Study Library

Separate resource knowledge from personal memory and External Context.

SQLite FTS first.

### Phase 5 — Study Skill

Expose structured Study tools to HoneyOS.

### Phase 6 — Active Recall

User summaries, quizzes, answers, scoring, explanations and source references.

### Phase 7 — Flashcards

Flashcards and spaced repetition.

### Phase 8 — Local LLM

Use local small model only for constrained structured extraction tasks.

### Phase 9 — Adaptive Planner

Adjust future study plans using actual progress and performance.

## Frozen Principles

- Study Library is not Personal Memory.
- Study Library is not External Context.
- StudyPlan structured data is runtime source of truth.
- Markdown is interchange.
- One validator handles all plan input channels.
- Pomodoro reuses existing scheduler.
- Local LLM does not make complex planning decisions.
- Existing working HoneyOS functionality must not regress.
