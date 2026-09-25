# Selective Loading v1 Freeze

Date: 2026-09-25
Branch: `feature/chat-message-batching`

## Frozen behavior

- Deterministic rules perform real synchronous toolset narrowing.
- Companion semantic toolsets remain available when configured.
- Recall -> memory + session_search.
- Files -> file.
- Research -> web.
- Automation -> todo + cronjob.
- Ambiguous turns do not wait for local Qwen.
- Ambiguous/error fallback uses the conservative core:
  companion_profile, companion_memory, proactive_companion,
  memory, session_search, file, web.
- Local Qwen remains async shadow-only.
- No fallback to the full configured toolset.

## Verified gates

- Routing tests passed before freeze.
- Live SELECTIVE_LOADING_V1 log confirmed the real agent received the narrowed automation set:
  companion_memory, companion_profile, cronjob, proactive_companion, todo.
- Shadow gates passed for chat, recall, files, research, and automation.

## Excluded unrelated work

Model selector/global-model persistence, Chat->Study Library upload,
Study changes, unrelated memory changes, and unrelated frontend build artifacts
are intentionally not part of this freeze commit.
