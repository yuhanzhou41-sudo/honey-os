import { describe, expect, it } from "vitest";

import {
  parseStickerChatMessage,
  stickerChatMessage,
  stickerReactionLabel,
} from "./stickers";

describe("C1.2 sticker chat message helpers", () => {
  it("serializes a local sticker as a compact semantic message", () => {
    const id = "a".repeat(32);
    expect(stickerChatMessage({ id, tags: ["happy"] })).toBe(
      `[表情包：开心]<honeyos-sticker:${id}>`,
    );
  });

  it("parses persisted sticker messages for local rendering", () => {
    const id = "b".repeat(32);
    expect(parseStickerChatMessage(`[表情包：无语]<honeyos-sticker:${id}>`)).toEqual({
      id,
      label: "无语",
    });
  });

  it("does not treat ordinary text as a sticker message", () => {
    expect(parseStickerChatMessage("今天有点无语")).toBeNull();
    expect(stickerReactionLabel("does-not-exist")).toBe("表情");
  });
});
