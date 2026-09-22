# Phase 4 — Study Library

Status: FROZEN

Implementation commit:

    db19c977801f93d29d4fde164098f81734337dd2

## Scope

Phase 4 adds the canonical Study Library on top of the frozen Study Core and Files / Attachment Core.

Implemented:

- StudyResource CRUD through StudyService
- Attachment -> StudyResource boundary by attachment_id
- textual attachment extraction for UTF-8 text formats
- study_resource_content derived-text side table
- SQLite FTS5 study_resource_fts index
- title / course / content search with snippets
- canonical /api/study/resources/* HTTP API
- Study Library frontend
- textual attachment upload / selection
- course filtering
- indexed-content viewer
- StudyResource deletion without deleting the underlying Attachment

## Storage

Canonical database:

    ~/.honeyos/study/study.db

Attachment storage remains independently owned by:

    ~/.honeyos/files/

Study Library does not write textbook or resource content into Personal Memory,
External Context, Diary, DeepSeek context, or legacy Companion Study.

## Extraction boundary

Phase 4 supports textual resources only:

- .txt
- .md / .markdown
- .json
- .csv
- .tsv
- .xml
- text/*

PDF / Office extraction is intentionally deferred to a later phase.

## Verification

- Phase 4 focused tests: PASS
- Full Study tests: PASS
- Full Files tests: PASS
- Combined Study + Files: 120 passed
- Frontend tests: 23 passed
- Frontend build: PASS
- Real Gateway StudyResource create/search/content/delete: PASS
- SQLite FTS5: PASS
- Gateway restart persistence: PASS
- canonical SQLite direct verification: PASS
- StudyResource delete / derived index cleanup: PASS
- Attachment ownership separation: PASS
- legacy Companion Study non-write: PASS

## Frozen boundary

Future phases may consume StudyResource and Study Library APIs but must not:

- merge Study Library into Personal Memory
- dual-write canonical and legacy Study
- make StudyResource own/delete Attachment
- replace StudyService as the canonical Study application boundary
- silently treat unsupported binary files as successfully indexed
