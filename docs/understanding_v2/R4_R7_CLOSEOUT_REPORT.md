# R4–R7 closeout report

Date: 2026-11-22 (Asia/Shanghai), closeout update 3

Repository: `HoneyOS-r4-r5-development-v2`, branch `master`, base commit
`2157f5d6aae786a96e4ac0e188510d6b1d5045e0`. All closeout work is currently
uncommitted. No production database, chat, diary, configuration, service,
release, remote branch, or paid model was accessed or changed.

## Honest Gate matrix

| Stage | Engineering evidence | Gate |
|---|---|---|
| R1 | Source contracts/index and full regression pass | PASS, synthetic/code only |
| R2 | Exact fact metadata adapter/index and regression pass | PASS, synthetic/code only |
| R3 | Bounded T/K/A ranker and scale tests pass | PASS, synthetic/code only |
| R4-01–06 | Contracts, program gate, store, proposer mock, maintenance/counterevidence pass | PARTIAL PASS |
| R4-07 | Saved-response commit, deterministic maintenance, bounded Gateway worker entry, live `ContinuitySourceResolver` recheck, and the live post-completed producer with an authorized original-text reader pass in isolation | PASS, synthetic/isolation; producer defaults off |
| R4-08 | Existing Gateway Memories page provides scoped edit/suppress/restore/forget management | PARTIAL PASS |
| R4-ENGINEERING | Live producer, authorization-first body reader, and an explicit off-by-default enable gate are bound; no production/model/release evaluation was performed | PASS for engineering scope, synthetic only |
| R4-MODEL | Synthetic smoke with local qwen3-4b: gate 5/5, pipeline 3/3, 9 grounded proposals; larger/multi-model quality not measured | PARTIAL PASS, synthetic only |
| R5-SYNTHETIC | Budget, replay cleanup, failure bounds, 10k scale, belief boundary and offline diary/state contexts pass; final primary transport is incomplete | PARTIAL PASS |
| R5-REAL | No real-user/model A/C trial | NOT_RUN |
| R5-TRANSPORT-STATE | `codex_app_server` and verified recall-state binding absent | BLOCKED |
| R6 | Backend actions, scope isolation, evidence lineage display, frontend tests/typecheck/build pass; current source validity remains `recorded_unverified`, and full graph layout is not implemented | PARTIAL PASS |
| R7 offline | Full regression, rollback semantics, idempotence, permissions, source-recheck recovery and scale pass | PASS for offline scope only |
| R7-RELEASE | No backup/restore rehearsal, production release audit, rollout or authorization | NOT_RUN |

Code existence, compilation, and mock tests are not treated as model quality,
real-user benefit, transport completion, or release approval.

## R4-07 recovery result

`process_completed_batch` commits a newly saved response through deterministic
maintenance and marks its job `completed`. A restart worker entry exists at
`GatewayRunner._recover_honeyos_u2_pending`; it scans a bounded page of
`response_saved` jobs and performs no model call.

Source recheck is now bound to the existing formal resolver:

- Before the single model call, `UnderstandingStore.save_job_evidence` records
  only evidence identity metadata: source system/record id, revision, event
  group, session, scope keys, purposes and original message refs. No source
  body is copied.
- `build_continuity_recovery_resolver` in `u2_sources.py` re-resolves every
  recorded source through `ContinuitySourceResolver` at commit time. A missing
  or forgotten row, a changed revision, or a withdrawn `analysis` permission
  blocks the whole job at `response_saved` instead of applying a stale result.
- `GatewayRunner._recover_honeyos_u2_pending` default-binds that resolver;
  `_u2_recovery_resolver` remains an explicit test/override injection point.
- `u2_maintenance.apply_proposal` keeps a replay guard: identical body plus
  already-recorded support/counter pairs return without creating a revision or
  strengthening evidence.

The live producer is now bound:

- `MemoryDistiller` already exposed an additive `post_completed_hook`.
  `GatewayRunner._schedule_honeyos_memory_distillation` binds
  `_honeyos_u2_post_completed` to it, so the producer runs only after the
  original completed transaction and inside its own `try/except`.
- `produce_after_distillation` (`u2_pipeline.py`) builds evidence only from
  `user_stated` structured memories written by this exact run, requires the
  source session to match, and re-resolves every memory through
  `ContinuitySourceResolver`. Revoked, expired, revised, or out-of-session
  sources are excluded; chapters are never used as evidence.
- `collect_run_evidence` / `build_run_body_reader` (`u2_sources.py`) read the
  original user turns cited by an already-authorized memory, capped at 1200
  characters. The reader cannot return text outside the completed batch.
- The proposal model spec comes only from the foreground turn's resolved
  `provider`/`model`/`api_mode`; an unresolved runtime returns
  `BLOCKED_MODEL_UNRESOLVED` without a request.
- At most one proposal request is issued per run (`retries=0`, no automatic
  resend), gated by signals and a daily call budget. Jobs are keyed by the
  distillation `run_id`, so duplicate scheduling skips and restart recovery
  reuses the saved response.
- Enablement is explicit and off by default:
  `memory.distillation.understanding.enabled=false`, with `namespace` and
  `max_daily_calls` (default 6).

Isolated end-to-end evidence (real SQLite continuity/U2 stores, actual Gateway
worker entry, no injected resolver):

- an allowed response completes once;
- a simulated crash after label application but before the `completed` receipt
  replays without changing label revision or evidence count;
- withdrawing the source keeps the job blocked at `response_saved`;
- restoring the row with a different revision also stays blocked;
- `model_calls` is always `0`.

Live-producer evidence (actual `_schedule_honeyos_memory_distillation` entry,
real distillation + continuity + U2 stores, temp home, fake model transports):

- a preference batch issues exactly **1** distillation call and **1** proposal
  call, then writes one label and marks the job `completed`;
- rescheduling the same completed source issues **0** additional calls;
- a factual batch still distils but the U2 gate issues **0** proposal calls;
- a failing proposal transport leaves `DistillationResult`/run `completed`,
  stores no label, and leaves the job `call_started` (no automatic resend);
- the body reader returns the original user text, drops a different session,
  and returns no evidence after the source is forgotten.

## R4-MODEL synthetic evaluation

Run on 2026-11-22 with the explicitly approved local llama.cpp model
`qwen3-4b-instruct-2507-Q4_K_M.gguf` at `127.0.0.1:8080`; no cloud or paid
provider, no production user data. Dataset:
`tests/honeyos/understanding_v2/fixtures/eval_manifest.json`,
SHA-256 `3c32ddfb…f6affc9`; raw report in
`docs/understanding_v2/R4_MODEL_SYNTHETIC_REPORT.json`.

- 5 synthetic cases: S01 preference, S18 fact-only, S20 chatter, S21 mixed,
  S22 conflict. Program gate matched all **5/5** expected gates.
- S18/S20 issued **0** model requests. The three RUN cases issued exactly
  **3** requests under a cap of 3, with no retry.
- All three RUN cases completed through `process_completed_batch`: **9**
  proposals and **9** labels in an isolated temp store.
- The first pass exposed a real prompt defect: the 4B model emitted
  `add`/`suggest` and non-contract categories, so the strict parser rejected
  every proposal. Enumerating the allowed operations and categories in
  `u2_proposer.SYSTEM_PROMPT` fixed contract compliance without relaxing the
  parser.
- Quality caveats: output drifted between Chinese/English and first/third
  person; one `support` operation created a new tentative label (deterministic
  maintenance behavior); the sample is tiny and single-model, so this is a
  contract/gate smoke result, not a broad model-quality claim.

## Remaining BLOCKED / NOT_RUN items (exact locations)

1. **`codex_app_server` transport.** The normal chat-completions path stamps
   and replays `api_content`. In `codex_app_server` mode, `conversation_loop`
   hands the raw current turn to `run_codex_app_server_turn` and deliberately
   skips sidecar stamping, so a controlled-context field and proof of the exact
   subprocess payload are still required. This transport remains excluded from
   active U2 injection.
2. **Honey state source.** No verified G2.1/state-to-recall interface is bound,
   so the state axis stays `bias=0 / state_axis_verified=false`.
3. **No verified Cognitive (non-continuity) body reader.** The live producer
   uses the continuity store only; a verified Cognitive reader is still absent.
4. **R4-MODEL** has only a 5-case single-model synthetic smoke; larger and
   multi-model semantic evaluation remains NOT_RUN. **R5-REAL and R7-RELEASE**
   still require explicit authorization for real-user samples, backup rehearsal
   and release work.

## Formal enablement and rollback

- **Current default:** runtime `off`; the live producer gate
  `memory.distillation.understanding.enabled` defaults to `false`. No label is
  generated or injected for a default install.
- **Recovery-only surface:** the worker is model-free and can only apply a
  previously saved response whose sources still pass live permission/revision
  checks. It cannot generate new understanding.
- **Enablement order:** set an explicit `understanding.namespace` and
  `understanding.max_daily_calls`, enable the producer while runtime stays
  `off`/`shadow`, run R4-MODEL, then R5 shadow/A-C evaluation; only then
  consider active injection.
- **Rollback:** set runtime mode to `off` and stop the producer. Keep the U2
  database; use `user_suppress` / `forget` for user-visible removal. Do not
  delete a database as the rollback mechanism. Removing the U2 store file is a
  last-resort manual step after an explicit backup.

## Test evidence

- Affected combined run (`tests/honeyos/understanding_v2`,
  `test_memory_distillation.py`, `test_continuity_gateway.py`,
  `test_companion_diary_automation.py`, `test_config.py`,
  `test_companion_prompt.py`): **101 passed**, 3 SQLite datetime-adapter
  deprecation warnings, 93.42 s. The 12-test U2 engineering file alone:
  **12 passed**. After the R4-MODEL prompt change, `tests/honeyos/understanding_v2`
  alone: **36 passed**, 12.34 s.
- R4-MODEL synthetic smoke: gate **5/5**, pipeline **3/3**, model requests
  **3/3 cap**, proposals **9**, paid cost **0**. No unrelated full regression
  was rerun.
- Previously recorded and not rerun: WSL full `python -m pytest tests/ -q` →
  **942 passed**, 3 SQLite datetime-adapter deprecation warnings, 506.08 s;
  frontend `pnpm test` → 14 files / 46 tests; typecheck and production build
  pass.
- Evaluation manifest remains synthetic; model requests: **0**, cost: **0**.

The prior Windows Python 3.14 asyncio hang was a restricted Proactor socket
problem. WSL `E_ACCESSDENIED` was sandbox launch policy. Neither is counted as
a product failure after the unrestricted WSL run passed.
