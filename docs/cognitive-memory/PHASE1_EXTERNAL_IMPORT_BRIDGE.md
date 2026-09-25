# Cognitive Memory Architecture v1
## Phase 1 — External Historical Import Bridge

Status: IN DEVELOPMENT — NOT FROZEN.

DeepSeek V2.1 faithful summaries -> external episodic memory + provenance.

No semantic consolidation, MemoryManager integration, chat retrieval, or native chat-memory generation is enabled in this phase.

Imported episodes use memory_origin=external, source_system=deepseek, source_scope=historical_import, and source_key=<summary_id>. Evidence provenance retains conversation_id, message key, exact quote, message time, path, branch root, conversation index, summary_id, and source batch.

Both summary-level and evidence-conversation-level source tombstones are checked before import. CLI defaults to dry-run; production writes require explicit --commit.
