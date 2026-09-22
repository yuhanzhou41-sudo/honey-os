# Phase 5.3 — Markdown Import + Adaptive Study Workspace

Status: Frozen
Date: 2026-09-23

## Implementation

Phase 5.3 implementation commit:

`1261ace4c7ddd8d92c521db475cf78ffa3048d0f`

Base before implementation:

`54a9e0a334f0428e3c1cf1fc08cba02ae90fb5a6`

## Scope

Phase 5.3 adds the browser-side Markdown import workflow and the adaptive Study workspace while preserving canonical StudyPlan / StudyTask / StudySession boundaries.

### Backend

Canonical endpoints:

- `POST /api/study/plans/import/preview`
- `POST /api/study/plans/import`

Canonical flow:

```text
StudyPlan Markdown
        ↓
parse_study_plan_markdown()
        ↓
validate_study_plan()
        ↓
preview StudyPlan
        ↓
user confirms exact same Markdown
        ↓
StudyService.import_markdown_plan()
        ↓
StudyRepository.save_plan()
```

Rules:

- Preview does not persist.
- Import reparses and revalidates.
- `source_type` is forced to `markdown_import`.
- Explicit duplicate plan IDs are rejected rather than overwritten.
- Import does not bypass `StudyService`.
- No canonical ↔ legacy dual-write.

### Frontend

Phase 5.3 introduces:

- Plan-first Study workspace.
- Flexible date / Day N navigation based on `start_date` and `end_date`.
- Arbitrary plan lengths; the UI is not fixed to seven days.
- Task grouping by `StudyTask.scheduled_date`.
- Empty-day rendering without inventing content.
- Markdown file selection.
- Backend preview before persistence.
- Explicit confirm step using the exact raw Markdown selected by the user.
- Collapsed Study tool rail:
  - Study Library
  - Review placeholder
  - Ask HoneyOS placeholder
- One floating / collapsible Pomodoro surface instead of a full Pomodoro panel in every task card.
- Existing plan/task manual editing remains available.

## Seven-day demo

Visual QA uses the recovered old Study MVP content:

`八科联考 · 21天冲刺（第一周示例）`

This is demo content only and does not constrain the canonical schema to exactly seven days.

Runtime verification:

- Date range: 2026-09-20 → 2026-09-26
- 38 canonical tasks
- 7 task dates
- `source_type=markdown_import`
- Pomodoro settings: 25 / 5 / 15 / 4

## Reserved UI only

Phase 5.3 reserves, but does not implement, the following future features:

- Sunlight points
- Small flowerpot / growth state
- Daily HoneyOS review / supervision
- Review Center
- Flashcards
- 10-question practice
- Wrong-answer notebook
- Study Q&A

These remain UI placeholders only.

Do not reconnect the old legacy Study reward database.

## Pomodoro boundary

The floating Pomodoro reuses the existing canonical StudySession / Classic Pomodoro backend.

Do not change:

- StudySession state machine
- scheduler
- backend authoritative timestamps
- plan-level cycle semantics

## Validation

Phase 5.3 runtime and regression gate passed:

- Direct `/health`: 200
- 7-day canonical demo import: PASS
- Runtime frontend bundle contains Phase 5.3 UI markers
- Invalid Markdown preview: 400
- Full Study backend regression: `60 passed`
- Focused StudyPage frontend tests: `4 passed`
- Full frontend regression before runtime gate: `27 passed`
- Frontend production build: PASS
- Vite >500 kB chunk warning remains non-blocking

## Git safety

Implementation commit was created with targeted staging.

`honeyos/gateway/platforms/api_server.py` contained unrelated dirty changes. Only these Phase 5.3 additions were staged:

- `_handle_study_preview_markdown_import`
- `_handle_study_import_markdown_plan`
- `/api/study/plans/import/preview`
- `/api/study/plans/import`

All unrelated Context Ingestion, legacy Study, reminders, model routing, proactive-message, and other worktree changes remained unstaged.

## Out of scope

Not implemented in Phase 5.3:

- Reward calculations
- Plant growth persistence
- Daily AI supervision
- Wrong-answer persistence
- Quiz generation
- Flashcard scheduling
- Study Q&A retrieval pipeline
- Local-model reranking
- Natural-language plan modification
- Planning request builder
- HoneyOS-generated plan creation
- StudyPlan schema v2 extensions
