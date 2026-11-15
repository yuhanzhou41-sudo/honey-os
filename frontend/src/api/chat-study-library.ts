import type { ChatInput } from "./chat";
import { referenceLocalStudyFile } from "./study";

export async function referenceChatStudyDocument(path: string) {
  return referenceLocalStudyFile(path);
}

export function studyDocumentMarker(id: string, title: string): string {
  const label = title.replace(/[\r\n【】]+/g, " ");
  return `📄 ${label} 【Study:${id}】`;
}

export function studyResourceIds(message: ChatInput): string[] {
  const text = typeof message === "string"
    ? message
    : message.flatMap((part) => part.type === "text" ? [part.text] : []).join("\n");
  const ids = Array.from(text.matchAll(/【Study:(resource_[a-f0-9]{32})】/g), (match) => match[1]);
  return [...new Set(ids)];
}
