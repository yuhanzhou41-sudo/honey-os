# Cognitive Memory Architecture v1
## Phase 0.1 — Source Identity Contract

Status: FROZEN after passing Phase 0.1 regression tests.

Core principle: **Storage identity separation, retrieval-time convergence.**

Imported history is not native remembered experience.

### Native
`memory_origin = "native"` and `source_system` must be `honeyos` or `honeyos_*`.

### External
`memory_origin = "external"` and every record must provide `source_system`, `source_scope`, and `source_key`. External memory may not use a HoneyOS-native source namespace.

### Non-impersonation invariant
External/imported history must never silently become a HoneyOS-native episode, shared experience, or current-state assertion merely because it was imported.

### Retrieval-time convergence
Future retrieval may combine native current state, native episodes, external historical evidence, procedural memory, and provenance, while preserving enough source identity to distinguish current/native understanding from historical/imported evidence.

### Critical conflict classes
Future reconciliation gives special protection to timeline, entity/person identity, explicit user preference, explicit correction, and current project state. External historical evidence must not silently overwrite conflicting native current state.

### Suppression
Source identity does not bypass content, subject, source, or memory tombstones.

### DeepSeek importer contract
The future DeepSeek V2.1 importer must use `memory_origin=external`, `source_system=deepseek`, `source_scope=historical_import`, and a stable `source_key`, with provenance/evidence preserved.

Schema version: `2`. Persistent identity fields: `memory_origin`, `source_system`, `source_scope`, `source_key`.
