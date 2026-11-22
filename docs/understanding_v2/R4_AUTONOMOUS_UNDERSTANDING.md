# R4 autonomous understanding — engineering status

Date: 2026-11-22. Plan: v2.1.

Implemented in the isolated E: snapshot:

- strict U2 DTO/proposal contracts and program-owned permission/state/grade;
- program-only Chinese/Unicode signal gate with fact/chatter/duplicate skips;
- bounded postings lookup and reuse boundary for the R3 ranker;
- separate explicitly initialized SQLite store, stable job id, atomic call issue,
  saved-response recovery state, evidence deduplication and policy epochs;
- one-request proposer with fixed prompt/schema, zero automatic retries;
- deterministic low/medium/high grading, counter-evidence dispute behavior;
- completed-batch U2 orchestration isolated from the original
  `DistillationResult` and now called by the live distiller through an explicit
  off-by-default post-completed hook;
- exact revision/permission-before-body utility, plus an authorization-first
  original-text reader for live evidence;
- list/explain/suppress/forget library and explicit `--home` CLI;
- unified exact-source dedup and total/graph token-budget composer;
- off/shadow/active fail-closed runtime boundary.

Not complete / not enabled:

- no production configuration, data, release, service restart, or real model call;
- a verified Cognitive (non-continuity) body reader is still absent;
- the live producer exists but is disabled by default
  (`memory.distillation.understanding.enabled=false`); it issues at most one
  no-retry proposal request from `user_stated` memories of the just-completed
  run, re-authorized through `ContinuitySourceResolver`, and failure is isolated
  from the distillation result. Restart recovery still rechecks metadata only and
  never calls a model;
- trusted Gateway management is present in the existing Memories page;
- active mode is not wired into system/api_content/codex_app_server;
- Honey-state interface is absent, so state bias remains zero;
- R4-MODEL synthetic smoke passed (5 gate cases, 3 local requests, 9 grounded
  proposals, local qwen3-4b); broader/multi-model semantic evaluation is
  NOT_RUN. R5-REAL and R5-TRANSPORT-STATE remain NOT_RUN/BLOCKED.

Current honest gate: **R4-07 and R4-MODEL synthetic smoke pass for isolated
engineering scope**, with the live producer default-off; real-user benefit,
transport completion and release remain NOT_RUN/BLOCKED.
