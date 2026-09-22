# Phase 4.5 — Document Extraction for Study Library

Status: **Frozen**

Implementation commit:

```text
bbc408834140d626a9cc2a2c3306a6622aac77d6
```

## Purpose

Phase 4.5 extends the frozen Phase 4 Study Library so supported document
attachments can be converted to text and indexed through the existing
StudyResource / study_resource_content / SQLite FTS5 pipeline.

This phase does **not** redesign the Study Library, Attachment Core,
StudyResource schema, API routes, Pomodoro system, scheduler, Memory, or
External Context.

## Frozen architecture

```text
PDF / DOCX / PPTX / XLSX
        ↓
Attachment Core
        ↓
StudyService
        ↓
shared document extraction utility
        ↓
study_resource_content
        ↓
SQLite FTS5
        ↓
existing Study Library API/UI
```

Canonical Study database remains:

```text
~/.honeyos/study/study.db
```

Canonical attachment storage remains:

```text
~/.honeyos/files/
```

Deleting a StudyResource still deletes the resource and derived index/content,
but does **not** delete its Attachment.

## Supported extraction

### Text formats

Existing Phase 4 behavior remains:

- TXT
- Markdown
- JSON
- CSV
- TSV
- XML
- text/*

### PDF

- text-layer PDFs only
- extraction via pinned `pypdf==6.18.0`
- page markers: `[Page N]`
- encrypted PDFs are rejected unless readable with empty password
- image-only / scanned PDFs with no extractable text are rejected explicitly
- no OCR

### DOCX

- local OOXML extraction
- paragraph text
- table text
- no Word runtime dependency
- no layout reconstruction

### PPTX

- local OOXML extraction
- slide order from `presentation.xml` relationships
- text boxes / titles / body / table text through DrawingML text nodes
- slide markers: `[Slide N]`
- no image understanding
- no chart or flowchart semantics

### XLSX

- existing local OOXML extraction retained
- workbook sheet order
- sheet labels
- cell values/basic row structure
- no spreadsheet formula engine

## Shared extraction boundary

Phase 4.5 reuses and extends:

```text
honeyos/tools/read_extract.py
```

The Study layer does not introduce a second document parser implementation.

For binary document attachments, `StudyService` writes attachment bytes to a
temporary file and calls the shared extraction utility. Attachment Core remains
unchanged.

## Dependency decision

`pypdf==6.18.0` is a core dependency for text-layer PDF extraction.

The repository's pinned uv toolchain is:

```text
uv 0.11.21
```

The lockfile was minimized so the Phase 4.5 lock diff contains only the pypdf
dependency and resolved package block; unrelated uv normalization churn was not
committed.

`uv lock --check` passed with the minimized lockfile.

## UI changes

Study Library upload/select support was extended to:

- .pdf
- .docx
- .pptx
- .xlsx

The existing Study Library UI structure remains unchanged.

The UI explicitly states that scanned PDFs and image content do not receive OCR
or visual understanding in Phase 4.5.

## Test and verification record

Focused Phase 4/4.5:

```text
9 passed
```

Combined Study + Files:

```text
125 passed
```

Combined execution uses:

```text
pytest --import-mode=importlib tests/honeyos/study tests/honeyos/files
```

because both suites contain several identical test module basenames.

Lock validation:

```text
uv 0.11.21 lock --check
PASS
```

Runtime API gate:

```text
GET /health
HTTP 200

GET /api/study/resources
HTTP 200
```

Local runtime probes must bypass the user's HTTP proxy for localhost:

```text
curl --noproxy '*'
```

Canonical PDF integration smoke passed:

```text
Attachment
→ StudyResource create
→ PDF extraction
→ FTS search
→ content read
→ resource delete
→ FTS cleanup
→ Attachment preserved
→ Study DB reopen verification
PASS
```

## Explicit non-goals

Not implemented in Phase 4.5:

- scanned PDF OCR
- PDF image recognition
- PPT image understanding
- chart semantics
- flowchart semantics
- vision model integration
- embeddings
- vector database
- legacy Office formats as canonical Study input
- Memory writes
- External Context writes
- Study Plan creation/import

## Freeze rule

Phase 4.5 is now frozen.

Future work must not redesign this extraction boundary or bypass
`StudyService` unless a verified defect is demonstrated.

Phase 5 must begin from the frozen Phase 4.5 implementation commit above.
