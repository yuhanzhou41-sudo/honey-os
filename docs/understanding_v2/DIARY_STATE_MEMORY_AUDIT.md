# Diary, state, and memory data-flow audit

The scheduled Gateway diary path selects the local owner's current companion
session, reads stored messages, keeps only companion-visible rows whose trusted
timestamp belongs to the target local date, and caps the result at the latest
120 rows. It loads the confirmed companion profile and calls
`generate_diary_entry`.

The actual model payload contains exactly:

- target date;
- confirmed companion profile fields;
- same-day user-authored diary entries that permit AI viewing;
- filtered same-day conversation rows.

The system prompt explicitly says only new user diary entries and conversation
rows are factual event sources. It does not load `MEMORY.md`, structured
long-term memories, Cognitive Memory, U2 labels, recent recall, or
`momentary_state.json`. Honey-generated earlier diary text is not read back as
input. After a diary is generated, normal memory distillation may be scheduled;
that downstream action does not retroactively change the diary prompt.

Offline A/B/C comparison used identical profile and same-day conversation:

- A: legacy/no U2 state;
- B: an initialized U2 store with neutral state;
- C: a valid synthetic positive/curious momentary state.

All three produced byte-identical diary messages, which is the expected current
contract: U2 and momentary state are not diary inputs. Therefore any observed
diary emotional variation may come from same-day conversation, profile,
user-authored diary content, temperature `0.9`, or model randomness. The
offline test proves payload boundaries only; it does not prove personality or
emotion changed.
