import { apiPath } from "./client";

export type StickerSort = "recent" | "least_used" | "largest";

export type StickerItem = {
  id: string;
  filename: string;
  preview_filename?: string | null;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  tags: string[];
  created_at: string;
  usage_count: number;
  last_used_at?: string | null;
};

export type StickerStatus = {
  count: number;
  limit: number;
  warning_threshold: number;
  warning: boolean;
  full: boolean;
  total_bytes: number;
  storage_root: string;
};

export const STICKER_REACTIONS = [
  ["happy", "开心"], ["laugh", "大笑"], ["love", "喜欢"], ["shy", "害羞"],
  ["comfort", "安慰"], ["hug", "抱抱"], ["sad", "难过"], ["cry", "哭"],
  ["angry", "生气"], ["annoyed", "无语"], ["shock", "震惊"], ["confused", "疑惑"],
  ["awkward", "尴尬"], ["sleepy", "困"], ["cheer", "加油"], ["celebrate", "庆祝"],
] as const;

async function jsonResponse<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(String(body?.error || `sticker request failed (${response.status})`));
    Object.assign(error, { body });
    throw error;
  }
  return body as T;
}

export async function fetchStickerStatus(): Promise<StickerStatus> {
  return jsonResponse(
    await fetch(apiPath("/api/companion/stickers/status"), {
      cache: "no-store",
      credentials: "same-origin",
    }),
  );
}

export async function listStickers(options: {
  tag?: string;
  sort?: StickerSort;
  limit?: number;
} = {}): Promise<{ stickers: StickerItem[]; status: StickerStatus }> {
  const params = new URLSearchParams();
  if (options.tag) params.set("tag", options.tag);
  if (options.sort) params.set("sort", options.sort);
  if (options.limit) params.set("limit", String(options.limit));
  const suffix = params.size ? `?${params.toString()}` : "";
  return jsonResponse(
    await fetch(apiPath(`/api/companion/stickers${suffix}`), {
      cache: "no-store",
      credentials: "same-origin",
    }),
  );
}

export async function uploadSticker(file: File, tag: string) {
  const form = new FormData();
  form.append("tag", tag);
  form.append("file", file);
  return jsonResponse<{ sticker: StickerItem; status: StickerStatus }>(
    await fetch(apiPath("/api/companion/stickers"), {
      method: "POST",
      body: form,
      credentials: "same-origin",
    }),
  );
}

export async function deleteSticker(stickerId: string) {
  return jsonResponse<{ deleted: true; status: StickerStatus }>(
    await fetch(apiPath(`/api/companion/stickers/${encodeURIComponent(stickerId)}`), {
      method: "DELETE",
      credentials: "same-origin",
    }),
  );
}

export async function markStickerUsed(stickerId: string) {
  return jsonResponse<{ sticker: StickerItem }>(
    await fetch(apiPath(`/api/companion/stickers/${encodeURIComponent(stickerId)}/used`), {
      method: "POST",
      credentials: "same-origin",
    }),
  );
}

export function stickerMediaUrl(stickerId: string) {
  return apiPath(`/api/companion/stickers/${encodeURIComponent(stickerId)}/media`);
}

export function stickerPreviewUrl(stickerId: string) {
  return apiPath(`/api/companion/stickers/${encodeURIComponent(stickerId)}/preview`);
}

export function stickerReactionLabel(tag: string | undefined): string {
  return STICKER_REACTIONS.find(([value]) => value === tag)?.[1] || "表情";
}

const stickerMessagePattern = /^\[表情包：([^\]\n]{1,40})\]<honeyos-sticker:([a-f0-9]{32})>$/;

export function stickerChatMessage(item: Pick<StickerItem, "id" | "tags">): string {
  return `[表情包：${stickerReactionLabel(item.tags?.[0])}]<honeyos-sticker:${item.id}>`;
}

export function parseStickerChatMessage(content: string): { id: string; label: string } | null {
  const match = String(content || "").trim().match(stickerMessagePattern);
  if (!match) return null;
  return { label: match[1], id: match[2] };
}
