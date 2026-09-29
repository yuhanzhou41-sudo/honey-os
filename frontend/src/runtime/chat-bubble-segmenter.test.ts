import { describe, expect, it } from "vitest";

import {
  assistantBubblesForDisplay,
  isStructuredChatTurn,
  legacyAssistantMessageBreak,
  segmentCasualAssistantText,
} from "./chat-bubble-segmenter";

describe("C1 streaming chat bubble segmenter", () => {
  it("matches the intended casual-chat example", () => {
    const text = "早上好呀snow，今天又在忙什么呢？昨天我们聊到xxx，你说xxx。早饭吃了什么呢？和我说说吧。";
    expect(assistantBubblesForDisplay(text, "早上好")).toEqual([
      "早上好呀snow",
      "今天又在忙什么呢？",
      "昨天我们聊到xxx，你说xxx。",
      "早饭吃了什么呢？",
      "和我说说吧。",
    ]);
  });

  it("seals an early bubble before the full reply is complete", () => {
    const result = segmentCasualAssistantText("早上好呀snow，今天");
    expect(result.sealed).toEqual(["早上好呀snow"]);
    expect(result.partial).toBe("今天");
  });

  it("does not split an incomplete dependency clause at a comma", () => {
    const text = "因为我今天早上起来得比较晚，所以到学校的时候已经快十点了。";
    expect(assistantBubblesForDisplay(text, "我今天睡过头了")).toEqual([text]);
  });

  it("does not split inside paired quotes or brackets", () => {
    const text = "我看到一句“如果今天很累，就早点休息。”觉得还挺适合你的。你现在还困吗？";
    expect(assistantBubblesForDisplay(text, "有点困")).toEqual([
      "我看到一句“如果今天很累，就早点休息。”觉得还挺适合你的。",
      "你现在还困吗？",
    ]);
  });

  it("keeps structured tasks in one assistant bubble", () => {
    const text = "第一点。第二点。第三点。";
    const user = "详细分析这段 Python 代码为什么报错，并给出修改步骤";
    expect(isStructuredChatTurn(user)).toBe(true);
    expect(assistantBubblesForDisplay(text, user)).toEqual([text]);
  });

  it("keeps legacy separators readable without using them for new generation", () => {
    expect(
      assistantBubblesForDisplay(
        `第一条${legacyAssistantMessageBreak}第二条${legacyAssistantMessageBreak}第三条`,
        "",
      ),
    ).toEqual(["第一条", "第二条", "第三条"]);
  });

  it("uses a safety cap instead of a target bubble count", () => {
    const text = "一。二。三。四。五。六。七。八。";
    const bubbles = assistantBubblesForDisplay(text, "随便聊聊", 6);
    expect(bubbles).toHaveLength(6);
    expect(bubbles[0]).toBe("一。");
    expect(bubbles[5]).toContain("八。");
  });
});
