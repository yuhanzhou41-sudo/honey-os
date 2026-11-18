import { requestJson } from "./client";

export type WorkState = {
  enabled: boolean;
  work_id: string | null;
  session_id: string | null;
};

export type EventAccess = {
  grants: { source: string; expires_at: string }[];
  audit: { source: string; checked_at: string; allowed: number }[];
  events: Record<string, unknown>[];
};

export const companionAccess = {
  work: () => requestJson<WorkState>("/api/companion/work"),
  events: () => requestJson<EventAccess>("/api/companion/events"),
};

export const SOURCE_LABELS: Record<string, string> = {
  chat: "聊天",
  study: "学习",
  reminder: "提醒",
};
