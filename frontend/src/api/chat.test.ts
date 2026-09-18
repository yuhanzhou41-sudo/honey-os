import { describe, expect, it } from "vitest";

import {
  assistantMessageBreak,
  parseEventBlock,
  splitAssistantReply,
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

  it("keeps a normal assistant reply as one message", () => {
    expect(splitAssistantReply("一条完整回复")).toEqual(["一条完整回复"]);
  });

  it("splits an assistant reply into natural message bubbles", () => {
    expect(splitAssistantReply(`第一条${assistantMessageBreak}第二条${assistantMessageBreak}第三条`))
      .toEqual(["第一条", "第二条", "第三条"]);
  });

  it("merges overflow into the final allowed message", () => {
    const reply = Array.from({ length: 7 }, (_, index) => `消息${index + 1}`)
      .join(assistantMessageBreak);
    expect(splitAssistantReply(reply, 5)).toEqual([
      "消息1", "消息2", "消息3", "消息4", "消息5\n\n消息6\n\n消息7",
    ]);
  });
});
