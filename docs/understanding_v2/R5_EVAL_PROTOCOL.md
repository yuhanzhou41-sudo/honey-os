# R5 evaluation protocol

The checked-in manifest is synthetic and freezes case IDs, expected gates,
generation settings, and a SHA-256 reported by the evaluator. `dry-run` makes
no network request and reports the worst-case token plan. A capped
`synthetic-model` smoke ran against a loopback model after explicit approval
(R4-MODEL synthetic smoke); full R5 A/C model evaluation remains blocked until
a larger R4-MODEL pass and an explicit request cap/provider authorization are
supplied. A/C comparisons use identical source snapshots, budgets, model
settings, randomized presentation, and blind labels. Gate, retrieval, label,
final-request, and answer scores are reported separately.

Real user text, model responses, and private ratings must not be committed.
