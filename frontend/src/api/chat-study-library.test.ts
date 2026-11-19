import { describe, expect, it } from "vitest";

import {
  chatStudyDocumentContext,
  limitChatDocumentContext,
  studyResourceContentToText,
  type ChatStudyDocument,
} from "./chat-study-library";

describe("chat study library helpers", () => {
  it("extracts common study-resource text shapes", () => {
    expect(studyResourceContentToText("hello")).toBe("hello");
    expect(studyResourceContentToText({ text: "alpha" })).toBe("alpha");
    expect(studyResourceContentToText({ data: { content: "beta" } })).toBe("beta");
  });

  it("does not stringify unknown metadata as fake document text", () => {
    expect(studyResourceContentToText({ pages: 20, mime: "application/pdf" })).toBe("");
  });

  it("marks oversized extracted text as truncated", () => {
    const result = limitChatDocumentContext("x".repeat(80001));
    expect(result.text).toHaveLength(80000);
    expect(result.truncated).toBe(true);
  });

  it("builds an explicit resource-backed context block", () => {
    const document: ChatStudyDocument = {
      id: "a:r",
      attachmentId: "a",
      resourceId: "r",
      name: "notes.pdf",
      text: "document body",
      truncated: false,
    };
    const context = chatStudyDocumentContext(document);
    expect(context).toContain("notes.pdf");
    expect(context).toContain("resource_id：r");
    expect(context).toContain("document body");
  });
});
