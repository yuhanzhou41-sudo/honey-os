import { describe, expect, it } from "vitest";

import { reactionForEmoji, stableStickerIndex } from "./sticker-reactions";

describe("C1.2 sticker reactions", () => {
  it("maps common standalone reactions", () => {
    expect(reactionForEmoji("🥺")).toBe("comfort");
    expect(reactionForEmoji("😂")).toBe("laugh");
    expect(reactionForEmoji("😑")).toBe("annoyed");
    expect(reactionForEmoji("😴")).toBe("sleepy");
  });

  it("returns null for unmapped emoji", () => {
    expect(reactionForEmoji("🧬")).toBeNull();
  });

  it("selects deterministically inside the candidate range", () => {
    expect(stableStickerIndex("message-1🥺", 4)).toBe(stableStickerIndex("message-1🥺", 4));
    expect(stableStickerIndex("message-1🥺", 4)).toBeLessThan(4);
  });
});
