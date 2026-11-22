# R7 offline readiness

Only production-independent checks were advanced. Synthetic tests cover
bounded composition, token caps, management scope isolation, pagination,
idempotent off behavior, replay cleanup, management rollback semantics, and
saved-response recovery through the actual Gateway worker entry with the
existing continuity source resolver. Recovery rechecks live permission and
revision, never calls a model, and does not create a second revision or evidence
row when replayed after a crash.

No release was inspected or changed, no backup claim was made, and no runtime
configuration/service was touched. Rollback remains: set runtime `off`, stop
the producer, keep the U2 database, and use suppress/forget for user-visible
removal; deleting a database is not the rollback mechanism.

R7-RELEASE remains NOT_RUN. It still requires the mandatory R5 gates, minimum
management acceptance, an explicit release authorization, a verified backup
and restore exercise, actual transport testing, and off → shadow → limited
active rollout evidence.
