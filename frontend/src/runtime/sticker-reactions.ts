export type StickerReaction =
  | "happy" | "laugh" | "love" | "shy" | "comfort" | "hug"
  | "sad" | "cry" | "angry" | "annoyed" | "shock" | "confused"
  | "awkward" | "sleepy" | "cheer" | "celebrate";

const REACTION_BY_EMOJI: Record<string, StickerReaction> = {
  "😀": "happy", "😃": "happy", "😄": "happy", "😁": "happy", "😊": "happy",
  "😂": "laugh", "🤣": "laugh",
  "❤️": "love", "❤": "love", "😍": "love", "🥰": "love", "😘": "love",
  "🙈": "shy", "😳": "shy",
  "🤗": "hug", "🫂": "hug", "🥺": "comfort",
  "😢": "sad", "😞": "sad", "☹️": "sad", "☹": "sad", "😭": "cry",
  "😠": "angry", "😡": "angry", "😤": "angry",
  "😑": "annoyed", "😒": "annoyed", "🙄": "annoyed",
  "😮": "shock", "😱": "shock", "🤯": "shock",
  "🤔": "confused", "😕": "confused", "🫤": "confused",
  "😅": "awkward", "😬": "awkward",
  "😴": "sleepy", "🥱": "sleepy", "💪": "cheer",
  "🎉": "celebrate", "🥳": "celebrate", "✨": "celebrate",
};

export function reactionForEmoji(emoji: string): StickerReaction | null {
  return REACTION_BY_EMOJI[emoji.trim()] || null;
}

export function stableStickerIndex(seed: string, size: number): number {
  if (size <= 1) return 0;
  let hash = 2166136261;
  for (let index = 0; index < seed.length; index += 1) {
    hash ^= seed.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % size;
}
