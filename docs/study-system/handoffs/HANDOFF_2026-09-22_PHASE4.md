# HoneyOS Study System — Phase 4 Handoff

Phase 4 is frozen.

Implementation commit:

    db19c977801f93d29d4fde164098f81734337dd2

Canonical architecture:

    StudyPage
      -> /api/study/*
      -> StudyService
      -> StudyRepository / StudySessionStore
      -> ~/.honeyos/study/study.db

Study Library architecture:

    Files / Attachment Core
      -> attachment_id
      -> StudyResource
      -> study_resource_content
      -> SQLite FTS5
      -> StudyService
      -> /api/study/resources/*

Phase 4 does not change the frozen Pomodoro scheduler model.

The next planned phase is Phase 5 — Study Plan Creation & Import.

Planned three StudyPlan creation channels:

1. honeyos_generated
   - HoneyOS generates a canonical StudyPlan from a fixed structured template.
   - Later natural-language modifications must still be translated into canonical StudyService operations.

2. markdown_import
   - User may fill a planning-request helper and export Markdown.
   - The user may combine that Markdown with schedules/materials in another model.
   - Returned StudyPlan Markdown must go through parser -> validation -> preview -> StudyService import.
   - Markdown is an interchange format, not the database.

3. manual
   - User creates and edits StudyPlan / StudyTask directly.

All three channels converge on the same canonical StudyPlan / StudyTask models.
source_type records provenance only and must not prevent later manual edits.

File transfer convention:

Windows:
    D:\HoneyOS-Transfer

WSL:
    /mnt/d/HoneyOS-Transfer
