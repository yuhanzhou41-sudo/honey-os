# R5 shadow / A-C report

Date: 2026-11-22 (Asia/Shanghai)

## Result

- R5-01: partial pass. Shared bounded composition, stable source/revision
  dedupe, graph cap, policy epoch filtering, explicit inference wrapper, and
  final `api_content` helper coverage are implemented. Production readers and
  codex_app_server final-wire integration remain blocked by R4 engineering.
- R5-02: partial pass. Off and shadow cannot inject; active requires explicit
  authorization. Missing state is neutral and a supplied numeric state is
  clamped to [-0.15, 0.15]. No verified Honey state source exists, so the state
  axis and the user's codex_app_server transport remain BLOCKED.
- R5-03: partial pass. Resolver work has a total deadline and bounded worker
  capacity. U2 blocks have stable markers and can be removed on a policy epoch
  change without changing the clean user message. Live cache/session epoch
  wiring is not enabled.
- R5-04: dry-run infrastructure and scale test implemented. A capped
  R4-MODEL synthetic smoke (5 gate cases, 3 local requests) passed; actual R5
  A/C model evaluation remains NOT_RUN pending a larger R4-MODEL pass and
  request authorization.
- R5-05: NOT_RUN. No production chat was read and no real sample was sent.
- R5-06: R5-SYNTHETIC PARTIAL; R5-REAL NOT_RUN;
  R5-TRANSPORT-STATE BLOCKED. Active remains unavailable by default.

## Rollback

Set runtime mode to `off`; this returns no candidates/context and performs no
injection. Remove only the R5 test/evaluator/report additions and the additive
U2 context/runtime/helper changes. Do not delete R1-R4 data, labels, or
suppression records. A policy change must continue to strip prohibited derived
blocks from new requests.
