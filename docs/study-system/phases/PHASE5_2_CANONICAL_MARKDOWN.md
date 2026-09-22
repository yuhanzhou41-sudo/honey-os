# Phase 5.2 — Canonical StudyPlan Markdown

Status: **Frozen**

Phase 5.2 is a **zero-code acceptance phase**.

No new implementation commit was required because the canonical StudyPlan
Markdown codec, validation gate, fixtures, and semantic round-trip tests were
already introduced and frozen in Phase 0.

Canonical implementation provenance:

```text
b40e319a2c59b104fd417f856c95858def843718
```

Current Phase 5.1 baseline:

```text
88e71ffee07749ac1973f1e7bbe2db2cc4cdd406
```

## Frozen boundary

```text
StudyPlan
   ↕
Canonical Markdown codec
   ↕
study_plan.md
```

Markdown is an interchange format only.

It is not:
- a database
- a second Study persistence layer
- a replacement for StudyRepository
- a bypass around canonical validation

## Canonical implementation

Parser/exporter:

```text
honeyos/study/markdown.py
```

Validation:

```text
honeyos/study/validation.py
```

Canonical validation rule:

```text
Markdown import
HoneyOS-generated plan
manual/canonical StudyPlan
        ↓
validate_study_plan()
        ↓
StudyPlan v1
```

Imported Markdown plans and future HoneyOS-generated plans must pass the same
canonical StudyPlan validator.

## Markdown format

A StudyPlan Markdown document:

1. begins with YAML front matter
2. requires `study_plan_version: 1`
3. contains plan metadata in front matter
4. uses `# Goals`
5. uses `# Schedule`
6. groups tasks under ISO date headings:
   `## YYYY-MM-DD`
7. uses Markdown task items
8. supports task metadata including:
   - id
   - duration
   - review
   - description
   - status
   - order

Unknown task metadata is rejected.

Tasks before a schedule-date heading are rejected.

Invalid YAML, invalid schema versions, invalid plan dates, tasks outside the
plan date range, and other canonical StudyPlan validation failures are rejected.

## Source type

When source_type is absent from imported Markdown, parsing defaults to:

```text
markdown_import
```

The canonical StudyPlan model already supports:

```text
manual
markdown_import
honeyos_generated
```

## Semantic round-trip

Runtime timestamps are deliberately excluded from interchange equality.

Semantic round-trip comparison uses:

```text
semantic_plan_dict()
```

and preserves:

- schema_version
- title
- description
- start_date
- end_date
- status
- Pomodoro timing fields
- source_type
- goals
- task ids
- task titles/descriptions
- scheduled dates
- planned minutes
- task statuses
- order indexes
- review_required

Required invariant:

```text
Markdown
→ parse
→ validate
→ StudyPlan
→ export
→ parse
→ semantic equality
```

Database invariant:

```text
Markdown
→ StudyPlan
→ StudyRepository
→ StudyPlan
→ Markdown
→ StudyPlan
→ semantic equality
```

## Provenance audit

The following files were all introduced in Phase 0 and have not changed since:

```text
honeyos/study/markdown.py
honeyos/study/validation.py
tests/honeyos/study/test_markdown.py
tests/honeyos/study/test_repository.py
tests/honeyos/study/fixtures/minimal.md
tests/honeyos/study/fixtures/medical_exam.md
tests/honeyos/study/fixtures/invalid.md
```

Diff from Phase 0 implementation to the Phase 5.1 baseline for this codec scope:

```text
empty
```

## Verification

Canonical Markdown focused verification:

```text
20 passed
```

Full Study regression:

```text
54 passed
```

No code changes were required for Phase 5.2.

## Explicit non-goals

Phase 5.2 does not add:

- upload UI
- import preview UI
- user confirmation workflow
- API import endpoint
- automatic persistence from uploaded Markdown
- HoneyOS-generated planning
- natural-language planning
- LLM calls
- StudyResource integration
- Memory writes
- External Context writes

Those belong to later Phase 5 steps.

## Freeze rule

The Phase 0 canonical Markdown codec is now formally accepted as the frozen
Phase 5.2 interchange contract.

Later phases may call this codec, but should not create a parallel Markdown
format or bypass `validate_study_plan()` without a verified defect.
