import {
  apiPath,
  fetchWithLocalSessionRecovery,
  requestJson,
} from "./client";

export type AttachmentStatus = "ready" | "deleted" | "failed";
export type AttachmentSourceType = "upload" | "chat" | "study" | "import";

export type Attachment = {
  id: string;
  original_filename: string;
  object_key: string;
  declared_mime_type: string;
  inferred_mime_type: string;
  size_bytes: number;
  sha256: string;
  source_type: AttachmentSourceType;
  status: AttachmentStatus;
  created_at: string;
  updated_at: string;
};

export const listAttachments = () =>
  requestJson<{ attachments: Attachment[] }>("/api/attachments");

export async function uploadAttachment(
  file: File,
  sourceType: AttachmentSourceType = "upload",
): Promise<{ attachment: Attachment }> {
  const form = new FormData();
  form.append("source_type", sourceType);
  form.append("file", file, file.name);

  const response = await fetchWithLocalSessionRecovery(
    apiPath("/api/attachments"),
    {
      method: "POST",
      credentials: "same-origin",
      body: form,
      headers: { Accept: "application/json" },
    },
  );

  let payload: {
    attachment?: Attachment;
    error?: string | { message?: string };
    message?: string;
  } = {};

  try {
    payload = await response.json();
  } catch {
    // Local gateway can transiently return an empty body during restart.
  }

  if (!response.ok || !payload.attachment) {
    const message =
      typeof payload.error === "string"
        ? payload.error
        : payload.error?.message ||
          payload.message ||
          `attachment_upload_failed:${response.status}`;
    throw new Error(message);
  }

  return { attachment: payload.attachment };
}
