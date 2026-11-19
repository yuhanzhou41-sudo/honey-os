import { uploadAttachment } from "./attachments";
import {
  createStudyResource,
  getStudyResourceContent,
} from "./study";

export const CHAT_DOCUMENT_ACCEPT = [
  ".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".xml",
  ".pdf", ".docx", ".pptx", ".xlsx",
  "text/*",
  "application/json",
  "application/xml",
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
].join(",");

export const CHAT_DOCUMENT_CONTEXT_LIMIT = 80000;

export type ChatStudyDocument = {
  id: string;
  attachmentId: string;
  resourceId: string;
  name: string;
  text: string;
  truncated: boolean;
};

function firstTextLike(value: unknown): string {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";

  const record = value as Record<string, unknown>;
  for (const key of ["text", "content", "plain_text", "extracted_text", "body", "markdown"]) {
    const candidate = record[key];
    if (typeof candidate === "string" && candidate.trim()) return candidate;
  }
  return "";
}

export function studyResourceContentToText(value: unknown): string {
  const direct = firstTextLike(value);
  if (direct) return direct;

  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["data", "document", "resource", "payload"]) {
      const nested = firstTextLike(record[key]);
      if (nested) return nested;
    }
  }
  return "";
}

export function limitChatDocumentContext(text: string) {
  const normalized = String(text || "").trim();
  if (normalized.length <= CHAT_DOCUMENT_CONTEXT_LIMIT) {
    return { text: normalized, truncated: false };
  }
  return {
    text: normalized.slice(0, CHAT_DOCUMENT_CONTEXT_LIMIT),
    truncated: true,
  };
}

export async function uploadChatStudyDocument(
  file: File,
  sessionId?: string,
): Promise<ChatStudyDocument> {
  const { attachment } = await uploadAttachment(file, "chat");
  const { resource } = await createStudyResource({
    attachment_id: attachment.id,
    title: attachment.original_filename || file.name,
    resource_type: "document",
    course_or_subject: "",
    metadata: {
      source: "chat",
      ...(sessionId ? { chat_session_id: sessionId } : {}),
    },
  });

  const contentPayload = await getStudyResourceContent(resource.id);
  const extracted = studyResourceContentToText(contentPayload.content);
  const limited = limitChatDocumentContext(extracted);

  return {
    id: `${attachment.id}:${resource.id}`,
    attachmentId: attachment.id,
    resourceId: resource.id,
    name: attachment.original_filename || file.name,
    text: limited.text,
    truncated: limited.truncated,
  };
}

export function chatStudyDocumentContext(document: ChatStudyDocument): string {
  const header = [
    "[HoneyOS 学习资料库文档]",
    `文件名：${document.name}`,
    `resource_id：${document.resourceId}`,
    `attachment_id：${document.attachmentId}`,
    document.truncated
      ? "说明：当前聊天上下文只附带了文档前 80000 个字符；完整原文件已保存在学习资料库。"
      : "说明：完整原文件已保存在学习资料库。",
  ].join("\n");

  if (!document.text) {
    return `${header}\n\n当前没有可直接提取的文本内容；请根据 resource_id 说明这一限制，不要假装已经读取正文。`;
  }
  return `${header}\n\n--- 文档提取文本开始 ---\n${document.text}\n--- 文档提取文本结束 ---`;
}
