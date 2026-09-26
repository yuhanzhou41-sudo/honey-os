# Freeze — G2.1A.1 Name Invariant Fix

Date: 2026-09-26
Status: PASS / FROZEN

## Purpose

Preserve the distinction between:

- product identity: `HoneyOS`
- companion personal name: optional and currently unset

The companion personal name must remain an empty variable when no explicit name has been assigned.

## Invariant

```text
product identity = HoneyOS

companion personal name = ""

empty companion_name
    remains empty
    through profile
    through distillation
    through backend profile payload
    through frontend state

no layer silently converts it to "Honey"
```

## Production changes

### `honeyos/companion/distillation.py`

Removed the `"Honey"` fallback for an unset `companion_name`.

Before:

```python
"companion_name": str(supplied_profile.get("companion_name") or "Honey")
```

After:

```python
"companion_name": str(supplied_profile.get("companion_name") or "")
```

### `honeyos/companion/web.py`

Removed `DEFAULT_COMPANION_NAME = "Honey"` from the personal-name path.

An unset managed companion name remains empty in the backend profile response.

### `frontend/src/runtime/honey-store.ts`

Removed frontend personal-name fallback to `"Honey"`.

An unset companion name remains empty in client state.

## Regression tests

Updated:

- `tests/honeyos/test_memory_distillation.py`
- `tests/honeyos/test_companion_web.py`

Validated:

```text
test_memory_distillation.py + test_companion_web.py
84 passed

test_companion_profile_store.py
7 passed

test_companion_prompt.py
20 passed

focused frontend regression set
29 passed

frontend production build
PASS
```

Total relevant backend regression tests: **111 passed**.

Focused frontend regression tests: **29 passed**.

## Known unrelated baseline issue

The full frontend suite currently has two failures in:

```text
src/features/study/StudyPage.test.tsx
```

Both fail because the test fixture does not render the expected text `Original task`.

These failures are outside the G2.1A.1 change surface.

No G2.1A.1 file modifies StudyPage or StudyPage tests.

## Scope explicitly unchanged

G2.1A.1 does not change:

- product identity `HoneyOS`
- G1 / G2 prompt behavior
- personality formation logic
- tool permissions
- memory authority
- explicit profile-update authority
- `companion_name` write permissions

## G2.1 continuation contract

Future Personality Formation work must preserve this invariant:

```text
companion_name is outside automatic personality formation
```

Automatic personality formation may never infer, generate, restore, or populate a personal name.

When calling the existing profile writer, G2.1 must omit `companion_name` entirely unless an explicit identity-setting path separately authorizes a name change.
