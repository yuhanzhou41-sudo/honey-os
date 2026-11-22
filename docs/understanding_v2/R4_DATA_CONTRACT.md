# U2 data contract

U2 is additive. Its SQLite database (schema v3) is explicitly initialized and
never migrates continuity, cognitive-memory, or chat databases. Model output may
only contain the seven proposal fields accepted by `Proposal.from_mapping`;
owner, permission, revision, grade and state are program-owned. Unknown
permission is denied. Stable job identity excludes graph revision and includes
source hash and pipeline version. Evidence is deduplicated by event group before
grading.

`job_evidence` stores metadata required for restart revalidation: evidence ref,
source system/record id, source revision, event group, session ref, scope keys,
purposes, occurred time and original message refs. It never stores source body
text. Recovery must resolve each row against the live source store before
applying a saved response; a missing, forgotten, revision-changed, or
non-analysis source blocks the job.
