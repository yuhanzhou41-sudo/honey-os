import { describe, expect, it } from "vitest";

import {
  emojiCodepointSlug,
  notoAnimatedEmojiUrls,
  pureAnimatedEmoji,
} from "./animated-emoji";

describe("C1.1 animated emoji helpers", () => {
  it("recognizes one standalone pictographic emoji", () => {
    expect(pureAnimatedEmoji("🥺")).toBe("🥺");
    expect(pureAnimatedEmoji("  😍  ")).toBe("😍");
  });

  it("does not replace normal text containing emoji", () => {
    expect(pureAnimatedEmoji("好呀🥺")).toBeNull();
    expect(pureAnimatedEmoji("🥺🥺")).toBeNull();
  });

  it("supports ZWJ and variation-selector sequences", () => {
    expect(pureAnimatedEmoji("❤️")).toBe("❤️");
    expect(pureAnimatedEmoji("👩‍⚕️")).toBe("👩‍⚕️");
  });

  it("builds Noto codepoint candidates with a variation-selector fallback", () => {
    expect(emojiCodepointSlug("❤️")).toBe("2764_fe0f");
    expect(notoAnimatedEmojiUrls("❤️")).toEqual([
      "https://fonts.gstatic.com/s/e/notoemoji/latest/2764_fe0f/512.webp",
      "https://fonts.gstatic.com/s/e/notoemoji/latest/2764/512.webp",
    ]);
  });
});
