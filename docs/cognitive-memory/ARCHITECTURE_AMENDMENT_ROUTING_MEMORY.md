# HoneyOS Architecture Amendment
## Cheap Turn Routing + Human-like Memory Boundaries

Status: DEVELOPMENT BASELINE. Runtime integration is not enabled by this change.

### Core routing principle
Do not let the expensive model decide what should never have been sent to it.

Per turn:
`Rules -> Local Qwen if ambiguous -> Context Route -> Model Route -> Main Agent`

The router selects intent, complexity, memory mode/domains, skill groups,
capabilities, model tier, and candidate memory signal. It does not answer the user.

### Zero-token rule path
Greetings, thanks, explicit reminders, explicit recall and obvious single-domain
requests should be routed deterministically.

`你好 -> no skills + memory none + local tier`

Router failure must never fall back to loading all skills.

### Local Qwen boundary
The local router receives only the user message, a compact skill-group manifest,
and a closed schema. It does not receive full skill prompts and cannot write memory.

Candidate memory signals:
- none
- episodic_candidate
- possible_preference
- critical_candidate

### Two-stage skill selection
Stage 1 selects a small group:
study, files, memory, coding, research, communication, automation, media, system.

Stage 2 (later) selects actual skills inside chosen groups. Full instructions load
only after routing.

### Memory modes
- none
- minimal
- topic
- precision
- reminiscence

### Suppression vs natural forgetting
- dormant: may reactivate
- superseded: historical, no longer current
- user_suppressed: explicit user forget, must not auto-reactivate

Only explicit user suppression creates a hard anti-resurrection boundary.
Natural forgetting and model-driven dormancy are reversible.

### Memory serves three continuities
- User memory: what HoneyOS understands about the user
- Relationship memory: how both sides have learned to interact
- Self-continuity: prior commitments, norms and established ways HoneyOS adopted

### Lightweight human-like mechanisms for later phases
- relationship domain
- association strength from repeated co-recall
- reminiscence weighted sampling
- open-loop/resolved conversational threads

Prefer SQLite/Python mechanisms over extra model calls.

### Non-goals of this step
No chat-runtime integration, MemoryManager changes, skill execution, permanent
memory writes, or local-Qwen calls during tests.
