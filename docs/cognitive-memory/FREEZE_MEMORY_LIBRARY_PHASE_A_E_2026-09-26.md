# Cognitive Memory Library — Phase A–E Freeze

Date: 2026-09-26

## Frozen scope

### Phase A+B
- Read-only Cognitive Memory Library API.
- Historical-memory UI separated from original HoneyOS memory.
- DeepSeek historical partitions, search and pagination.
- Original HoneyOS memory routes remain intact.
- No Cognitive Memory runtime retrieval integration.

### Phase C+D
- Detail view with provenance/evidence.
- User edits with audit history in `memory_feedback_events`.
- Recycle bin via `user_suppressed` plus memory tombstones.
- Restore reactivates the memory and lifts the active memory tombstone.
- Recycle-bin memories cannot be edited.

### Phase E
- Permanent delete is allowed only from recycle bin.
- UI uses two-step confirmation.
- API requires explicit `PERMANENT_DELETE` confirmation.
- Permanent delete removes episode payload, provenance/evidence,
  edit/restore feedback, and the old memory-level tombstone.
- A minimal active source tombstone is retained with
  `reason=user_permanent_delete` to block re-import resurrection.
- The retained tombstone does not preserve summary/evidence/edit text.

## Runtime boundary

Cognitive Memory remains disconnected from normal chat retrieval.
Runtime retrieval is a later phase.

## Validation

- Cognitive Memory backend tests: 41 passed.
- Targeted frontend tests: 8 passed.
- Frontend TypeScript/Vite build: PASS.
- SQLite integrity: ok.

Production state at freeze:

```json
{
  "episodes": 1984,
  "provenance": 7607,
  "feedback": 0,
  "tombstones": 1,
  "active_tombstones": 1,
  "external_active": 1984,
  "external_trash": 0,
  "permanent_delete_source_tombstones": 1,
  "facts": 0,
  "edges": 0,
  "salience": 0
}
```

## Isolation strategy

Shared files were already dirty before Memory Library development, so this
freeze must not commit them wholesale.

The freeze script reconstructs each shared file as:

`HEAD + (pre-Memory baseline -> current Memory implementation)`

Baselines:
- A+B pre-change: `/mnt/d/HoneyOS-Transfer/memory-library-phase-ab-backups/20260925-214058`
- C+D repository pre-change: `/mnt/d/HoneyOS-Transfer/memory-library-phase-cd-backups/20260925-221439`

Generated `honeyos/companion/react_dist` assets are intentionally excluded from
this isolated commit because the bundle aggregates unrelated frontend work.
Source + build validation is the canonical freeze boundary.

## Reopen criteria

Reopen Phase A–E only for verified defects in:
- view/detail/edit lifecycle,
- recycle-bin suppression/restore,
- permanent-delete erasure,
- anti-resurrection source tombstones.

Runtime retrieval work belongs to the next phase.
