const NOTO_ANIMATED_BASE = "https://fonts.gstatic.com/s/e/notoemoji/latest";

const SINGLE_EMOJI_SEQUENCE =
  /^(?:\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?(?:[\u{1F3FB}-\u{1F3FF}])?(?:\u200D\p{Extended_Pictographic}(?:\uFE0F|\uFE0E)?(?:[\u{1F3FB}-\u{1F3FF}])?)*)$/u;

export function pureAnimatedEmoji(content: string): string | null {
  const value = String(content || "").trim();
  if (!value || !SINGLE_EMOJI_SEQUENCE.test(value)) return null;
  return value;
}

export function emojiCodepointSlug(emoji: string, stripVariationSelectors = false): string {
  const parts: string[] = [];
  for (const char of emoji) {
    const codepoint = char.codePointAt(0);
    if (codepoint == null) continue;
    const hex = codepoint.toString(16).toLowerCase();
    if (stripVariationSelectors && (hex === "fe0f" || hex === "fe0e")) continue;
    parts.push(hex);
  }
  return parts.join("_");
}

export function notoAnimatedEmojiUrls(emoji: string): string[] {
  const full = emojiCodepointSlug(emoji);
  const stripped = emojiCodepointSlug(emoji, true);
  return [full, stripped]
    .filter(Boolean)
    .filter((value, index, all) => all.indexOf(value) === index)
    .map((slug) => `${NOTO_ANIMATED_BASE}/${slug}/512.webp`);
}
