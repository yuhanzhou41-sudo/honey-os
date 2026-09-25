# DeepSeek V2.1 Cognitive Memory Import Freeze

Date: 2026-09-25
Status: FROZEN

## Scope

This freeze covers the deterministic DeepSeek V2.1 -> Cognitive Memory import bridge only.

Included:
- `honeyos/memory/importers/__init__.py`
- `honeyos/memory/importers/deepseek_v21.py`
- `tests/honeyos/memory/test_phase1_deepseek_v21_importer.py`
- `docs/cognitive-memory/PHASE1_EXTERNAL_IMPORT_BRIDGE.md`

Excluded:
- runtime MemoryManager integration
- chat-time retrieval
- native HoneyOS memory replacement
- selective loading / turn-router experiments
- semantic consolidation
- Study System
- reminder work
- model switching

## Production import result

Input:
`~/.honeyos/deepseek_sol_summary_v2_1/run/all_summaries.jsonl`

Input SHA256:
`2a1cd984dfb484a26282dc5dd6d66197158467ad35cc34a91b03c634b298ad77`

Imported:
- episodes: 1985
- provenance rows: 7612
- invalid: 0
- suppressed: 0
- null `occurred_at`: 0
- external identity violations: 0
- provenance violations: 0
- time policy violations: 0
- time span errors: 0
- SQLite integrity check: ok
- second import: idempotent (`already_complete=1985`, `provenance_created=0`)

Time policy:
- representative `occurred_at` = latest evidence `message_time`
- preserved metadata:
  - `raw_time`
  - `evidence_time_start`
  - `evidence_time_end`
  - `time_mapping_policy=evidence_span_end`

Source identity:
- `memory_origin=external`
- `source_system=deepseek`
- `source_scope=historical_import`
- `source_key=<summary_id>`

Production DB backup before import:
`/mnt/d/HoneyOS-Transfer/deepseek-v2.1-production-import/20260925-211545/cognitive_memory.before_import.sqlite`

Backup SHA256:
`bcdaf52349497bf27305294f6387be36eb0fbbff2e21fc2f7941d40ddd2ce91a`

Production import evidence:
`/mnt/d/HoneyOS-Transfer/deepseek-v2.1-production-import/20260925-211545/`

Git HEAD before production import:
`767e2002b0a925ae01764428dc4246b4dcc8bf22`

## Runtime relationship

This freeze does NOT connect Cognitive Memory to HoneyOS chat runtime.

The original HoneyOS memory path remains intact. Cognitive Memory currently stores the imported DeepSeek history as an external memory layer with explicit provenance/source identity. A later runtime integration phase may query this layer, but must not silently replace, overwrite, or masquerade as native HoneyOS memory.

## Reopen conditions

Reopen this freeze only for a verified defect in:
- deterministic import validation
- source identity
- evidence/provenance preservation
- tombstone/suppression behavior
- idempotency
- time-span mapping

New UI/workflow automation should be implemented outside this frozen import core.
