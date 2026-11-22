# R6 UI and permissions

Date: 2026-11-22

The existing Memories page now contains a third `Honey 的理解` section. It
uses the existing U2 SQLite store and Gateway authentication rather than a new
review database or service. Labels show category, scope, evidence grade,
state, revision, and bounded body text. User edit, suppression, explicit
restore, and logical forget remain separate operations.

Gateway never accepts `owner` from the browser; the trusted local companion
owner is fixed server-side. Every request requires a lane and namespace, and
all reads/mutations recheck owner/lane/namespace. List responses are capped at
100 rows (the UI requests 50), use offset pagination, and therefore do not load
a 10,000-label graph. User edits are recorded as `user_edit`, reset grade to
low, and do not change evidence permissions. Restore produces
`needs_reassessment`/low and cannot inherit prior high confidence. Forget
removes derived body/evidence/postings but does not delete original chat.

No production data was used for screenshots or tests. Full graph layout,
source availability resolution, evidence text authorization, and browser
click-through remain partial; the UI does not display source text it cannot
prove is currently permitted. The restart-recovery path now rechecks sources
through `ContinuitySourceResolver` before committing a saved response, but the
management detail endpoint still reports lineage as `recorded_unverified`
because it does not perform that live lookup.
