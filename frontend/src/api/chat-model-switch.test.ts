import { describe, expect, it } from "vitest";

import {
  fetchChatSessionModel,
  setChatSessionModel,
} from "./chat";

describe("chat model switching API surface", () => {
  it("exports session model read and session model write helpers", () => {
    expect(typeof fetchChatSessionModel).toBe("function");
    expect(typeof setChatSessionModel).toBe("function");
  });
});
