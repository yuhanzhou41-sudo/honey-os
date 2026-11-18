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
      "早上好呀snow，",
      "今天又在忙什么呢？",
      "昨天我们聊到xxx，你说xxx。",
      "早饭吃了什么呢？",
      "和我说说吧。",
    ]);
  });

  it("seals an early bubble before the full reply is complete", () => {
    const result = segmentCasualAssistantText("早上好呀snow，今天");
    expect(result.sealed).toEqual(["早上好呀snow，"]);
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

  it("keeps all eight conversational units without losing the tail", () => {
    const units = ["先聊聊今天。", "你说得也对。", "我后来想了很久。", "这让我想起昨天。", "那时候挺开心的。", "还有一件事。", "你想听吗？！", "我们慢慢说。"];
    const text = units.join("");
    expect(assistantBubblesForDisplay(text, "随便聊聊")).toEqual(units);
    expect(assistantBubblesForDisplay(text, "随便聊聊").join("")).toBe(text);
    expect(assistantBubblesForDisplay(text.slice(0, -2), "随便聊聊").slice(0, -1))
      .toEqual(units.slice(0, -1));
  });

  it("recognizes paragraph boundaries but keeps a short response together", () => {
    expect(assistantBubblesForDisplay("我在呢", "")).toEqual(["我在呢"]);
    expect(assistantBubblesForDisplay("先坐一会儿\n\n我给你倒杯水", ""))
      .toEqual(["先坐一会儿", "我给你倒杯水"]);
  });

  it.each([
    "你看看这个。\n\n1. 第一步。\n2. 第二步。",
    "你看看这个。\n\n| A | B |\n|---|---|",
    "你看看这个。\n\n$E=mc^2$。",
    "看看 [这里](notes.md)。还可以再等等。",
    "你看看这个。\n\nhttps://example.com/?q=a。",
  ])("preserves Markdown and links in %s", (text) => {
    expect(assistantBubblesForDisplay(text, "你看看")).toEqual([text]);
  });

  it("preserves all legacy bubbles", () => {
    const units = Array.from({ length: 8 }, (_, index) => "消息" + index);
    expect(assistantBubblesForDisplay(units.join(legacyAssistantMessageBreak), "")).toEqual(units);
  });
});
