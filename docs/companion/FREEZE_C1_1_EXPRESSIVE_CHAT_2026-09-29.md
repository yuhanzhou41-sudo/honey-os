# C1 / C1.1 Natural + Expressive Chat Runtime — Frozen 2026-09-29

## Status

PASS after automated gates and live validation.

## Included behavior

- C1 delivery-owned streaming bubble segmentation.
- No model-managed target bubble count and no new special separator generation.
- Strong punctuation early display with weak-boundary completeness protection.
- Quote, bracket, parenthesis, and code protection.
- Structured tasks remain one coherent assistant response by default.
- Stop, regenerate, rollback, delete, retry, and proactive chat behavior preserved.
- Message actions are hidden by default and revealed only for a selected message.
- Assistant text bubbles use content-fit width; tool/activity panels remain full width.
- C1.1 allows occasional emoji/kaomoji in ordinary conversation.
- Structured tasks avoid decorative emoji/kaomoji by default.
- Standalone completed assistant emoji can render through Noto Animated Emoji.
- Noto load failure falls back to the native emoji.
- No extra model calls are introduced by C1 or C1.1.

## Live validation

Confirmed in the real HoneyOS chat UI:
- streaming bubble splitting works;
- message actions are unobtrusive;
- assistant bubble width follows content;
- casual emoji/kaomoji behavior is normal;
- standalone animated emoji works;
- structured responses remain normal.

## Deferred to C1.2

- local GIF/WebP/PNG StickerStore;
- in-product sticker import and cleanup;
- 360 warning / 400 hard limit;
- local-sticker reaction replacement with Noto fallback;
- no GitHub integration yet.
