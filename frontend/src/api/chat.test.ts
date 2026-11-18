import { describe, expect, it } from "vitest";

import {
  parseEventBlock,
  splitUserMessages,
  userMessageBreak,
} from "./chat";

describe("parseEventBlock", () => {
  it("parses named SSE events", () => {
    expect(parseEventBlock('event: assistant.delta\ndata: {"delta":"你好"}')).toEqual({
      name: "assistant.delta",
      payload: { delta: "你好" },
    });
  });

  it("ignores keepalive comments and invalid data", () => {
    expect(parseEventBlock(": keepalive")).toBeNull();
    expect(parseEventBlock("event: error\ndata: not-json")).toBeNull();
  });

  it("splits queued user messages without empty entries", () => {
    expect(splitUserMessages(`第一条${userMessageBreak} 第二条 `)).toEqual(["第一条", "第二条"]);
  });

});
