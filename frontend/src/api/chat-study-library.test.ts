import { describe, expect, it } from "vitest";

import { studyDocumentMarker, studyResourceIds } from "./chat-study-library";

const resource = "resource_" + "a".repeat(32);
const other = "resource_" + "b".repeat(32);

describe("chat document references", () => {
  it("restores one ID from repeated references in a mixed message", () => {
    const marker = studyDocumentMarker(resource, "笔记.txt");
    expect(studyResourceIds([
      { type: "text", text: marker + "\n" + marker },
      { type: "image_url", image_url: { url: "data:image/png;base64,ignored" } },
    ])).toEqual([resource]);
  });

  it("prevents a filename from adding a second resource reference", () => {
    const name = `note 【Study:${other}】.txt`;
    expect(studyResourceIds(studyDocumentMarker(resource, name))).toEqual([resource]);
    expect(studyResourceIds("A message without a valid resource")).toEqual([]);
  });
});
