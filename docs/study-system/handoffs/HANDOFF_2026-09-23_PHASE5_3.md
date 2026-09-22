# Handoff — HoneyOS Study System after Phase 5.3

Date: 2026-09-23

## Current frozen point

Phase 5.3 implementation:

`1261ace4c7ddd8d92c521db475cf78ffa3048d0f`

Phase 5.2 freeze docs:

`54a9e0a334f0428e3c1cf1fc08cba02ae90fb5a6`

## Current Study capabilities

### Canonical Study core

- StudyPlan / StudyTask CRUD
- Manual plan/task editor
- Plan status / goals / date range
- Classic Pomodoro settings
- StudySession backend
- Floating Pomodoro UI
- Study Library
- Attachment → StudyResource → extracted content → FTS5
- PDF text-layer extraction
- DOCX / PPTX / XLSX extraction
- Canonical StudyPlan Markdown parse / export / validation
- Markdown preview / confirm / import workflow
- Adaptive arbitrary-length Day-based plan workspace

### UI structure

Study opens into the plan workspace.

Secondary tools are collapsed by default:

- Study Library
- Review
- Ask HoneyOS
- Floating Pomodoro

Top area reserves future:

- Sunlight points
- Small flowerpot / growth state
- Daily review / supervision

These reserved items are not implemented yet.

## Important architectural boundaries

Canonical:

```text
StudyPage
  ↓
/api/study/*
  ↓
StudyService
  ↓
StudyRepository / StudySessionStore
  ↓
~/.honeyos/study/study.db
```

Legacy companion Study remains separate:

```text
/api/companion/study/*
~/.honeyos/companion/study.db
```

Do not reconnect canonical StudyPage to legacy Study.

Do not dual-write.

Study Library remains separate from:

- Personal Memory
- External Context
- DeepSeek imported context
- Diary
- Context Ingestion

## Phase 5.3 import contract

```text
Markdown
↓
preview endpoint
↓
canonical StudyPlan preview
↓
user confirms exact same raw Markdown
↓
import endpoint
↓
StudyService
↓
study.db
```

No frontend Markdown parser.

No server-side pending preview state.

## Demo plan

Canonical runtime demo:

`八科联考 · 21天冲刺（第一周示例）`

- 2026-09-20 → 2026-09-26
- 38 tasks
- 7 task dates
- source_type: markdown_import
- Pomodoro: 25 / 5 / 15 / 4

Use this for visual QA only.

The UI must remain compatible with arbitrary plan lengths.

## Working-tree warning

The repository still contains many unrelated dirty/untracked changes.

Never use:

```bash
git add .
git reset --hard
git clean -fd
```

`honeyos/gateway/platforms/api_server.py` especially contains unrelated worktree changes.

Future Study commits that touch it must use targeted staging only.

## Recommended next phases

### Study Review Core

Add canonical data structures for:

- wrong answers
- review items
- Study Library source references
- review history

### 10-question practice

Suggested flow:

```text
current plan / task / selected resources
↓
Study Library FTS5 retrieval
↓
optional local-model lightweight reranking / extraction
↓
question generation
↓
answering
↓
grading / explanation
↓
wrong answers persisted
```

### Study Q&A

Suggested flow:

```text
current plan + current day + current task
↓
Study Library retrieval
↓
optional local-model lightweight filtering
↓
HoneyOS answer when needed
```

### Flashcards

Later:

- Study Library → flashcards
- wrong answers → flashcards
- review queue
- spaced repetition

### Daily supervision / reflection

Later read compact daily Study summaries:

- completed / unfinished tasks
- focus sessions
- focused minutes
- quiz performance
- wrong-answer count
- review workload
- user note

Local small model can handle simple extraction, summarization, query generation, and candidate filtering.

HoneyOS main model should remain responsible for higher-level interpretation, complex reasoning, and plan adjustment.

## Still not implemented

- Reward calculations
- Plant growth logic
- Daily AI supervision
- Wrong-answer store
- Quiz engine
- Flashcard scheduler
- Study Q&A pipeline
- Local-model reranking helper
- Planning request builder
- HoneyOS plan generator
- Natural-language plan modification
