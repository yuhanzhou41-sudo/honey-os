import { describe, expect, it } from "vitest";

import { shouldSubmitChatOnEnter } from "./mobile-interactions";

describe("shouldSubmitChatOnEnter", () => {
  it("keeps Enter as a newline on coarse-pointer mobile devices", () => {
    expect(shouldSubmitChatOnEnter({
      key: "Enter",
      shiftKey: false,
      isComposing: false,
      coarsePointer: true,
    })).toBe(false);
  });

  it("submits Enter on desktop when composition is finished", () => {
    expect(shouldSubmitChatOnEnter({
      key: "Enter",
      shiftKey: false,
      isComposing: false,
      coarsePointer: false,
    })).toBe(true);
  });
});
