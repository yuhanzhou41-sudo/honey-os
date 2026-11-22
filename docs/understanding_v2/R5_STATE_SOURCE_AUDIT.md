# Honey state source audit

Date: 2026-11-22

The current tree has a real persisted module at
`honeyos/companion/momentary_state.py`. It derives nine temporary axes from
regular-expression matches in Honey's own assistant response, stores them in
`companion/momentary_state.json`, applies a three-hour half-life, and returns a
neutral state after twelve hours or malformed/missing data. The companion
profile injects its human-readable note for tone.

This is reusable as a temporary **tone** source, but it is not yet a reliable
R5 recall-ranking state axis: it is heuristic, based on generated assistant
wording rather than a separately observed internal state, has no candidate-to-
axis relevance contract, and the current U2 transport has no verified live
binding. Treating a generic positive/negative value as a ranking score would
invent semantics and could change recall unrelated to the question.

Decision: retain neutral U2 bias (`0.0`, `state_axis_verified=false`). Reuse the
existing source only after a controlled candidate-axis mapping and live
transport test exist. Do not create a second emotion store and do not infer a
state from production chats for this audit.

## Actual call chain and feedback risk

After a non-interrupted response and successful session persistence,
`agent/turn_finalizer.py` calls `update_momentary_state_from_turn` with Honey's
final response, not the user's message. Regex matches update nine `[0,1]` axes
in `companion/momentary_state.json`. Values decay with a three-hour half-life
and become neutral after twelve hours; missing/malformed files also return
neutral. On the next turn, `companion_profile_note` includes
`momentary_state_note`, and Gateway stages that note on the user-message
sidecar. Thus generated wording can influence the next prompt and create weak
linguistic reinforcement. Counterbalancing and expiry limit it, but do not make
it an independently observed emotion.

There is no candidate-to-axis relevance API. The U2/R3 recall input therefore
continues to receive `0.0` with `state_axis_verified=false`. Synthetic clamp,
decay, malformed/missing and expiry tests pass; they validate computation, not
the existence of a genuine internal feeling.

Future binding design: define a controlled mapping from candidate category to
one or more named axes, carry source version/update time, require freshness,
apply only a bounded reorder after permission filtering, and shadow-log the
score without text. It must be evaluated against neutral ordering before any
active use.
