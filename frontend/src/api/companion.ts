import { apiPath, requestJson } from "./client";

export type PersonalityTrait = { layer: string; key: string; statement: string };

export const fetchPersonalityTraits = () =>
  requestJson<{ traits: PersonalityTrait[] }>("/api/companion/personality");

export const savePersonalityTrait = (trait: Omit<PersonalityTrait, "statement"> & { statement: string | null }) =>
  requestJson<{ traits: PersonalityTrait[] }>("/api/companion/personality", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(trait),
  });

export type ReplyFeedback = { rating: "like" | "dislike"; note: string };

export type ChatMessage = {
  id?: number;
  role: "user" | "assistant";
  content: string;
  timeline_editable?: boolean;
  feedback?: ReplyFeedback | null;
};

export const saveReplyFeedback = (
  sessionId: string,
  sessionKey: string,
  messageId: number,
  feedback: ReplyFeedback | null,
) => requestJson<{ feedback: ReplyFeedback | null }>(
  `/api/sessions/${encodeURIComponent(sessionId)}/messages/${messageId}/feedback`,
  {
    method: "PUT",
    headers: { "Content-Type": "application/json", "X-HoneyOS-Session-Key": sessionKey },
    body: JSON.stringify(feedback ?? { rating: null }),
  },
);

export const fetchCompanionMessages = (
  sessionId: string,
  sessionKey: string,
  signal?: AbortSignal,
) =>
  requestJson<{ object: string; session_id: string; data: ChatMessage[] }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/messages?view=companion`,
    {
      signal,
      headers: { "X-HoneyOS-Session-Key": sessionKey },
    },
  );


export type TimelineState = { cursor: number; busy_start: number; busy_end: number };

export type CompanionProfileDetails = CompanionBootstrap["profile_details"];

export type MemoryItem = {
  id: string;
  kind: string;
  content: string;
  status: string;
  evidence?: string | null;
  created_at?: string | null;
  expires_at?: string | null;
  updated_at?: string | null;
  unavailable_source_count?: number;
  can_edit?: boolean;
};

export type HistoricalMemoryItem = {
  id: string;
  memory_kind: "episode";
  summary: string;
  occurred_at?: string | null;
  captured_at?: string | null;
  status: string;
  origin: "external";
  source_system: string;
  source_scope?: string | null;
  source_key?: string | null;
  confidence: number;
  partition: string;
  partition_label: string;
  time_start?: string | null;
  time_end?: string | null;
  raw_time?: string | null;
  provenance_count: number;
  deleted_at?: string | null;
};

export type HistoricalMemoryDetail = HistoricalMemoryItem & {
  metadata: Record<string, unknown>;
  revisions: Array<{
    id: string;
    event_type: string;
    created_at: string;
    payload: { actor?: string; old_summary?: string; new_summary?: string };
  }>;
  trash?: {
    tombstone_id: string;
    reason: string;
    deleted_at: string;
    restored_at?: string | null;
    active: boolean;
  } | null;
  provenance: Array<{
    id: string;
    source_system: string;
    source_type: string;
    source_id?: string | null;
    session_id?: string | null;
    message_id?: string | null;
    evidence_quote?: string | null;
    created_at: string;
    metadata: Record<string, unknown>;
  }>;
};

export type HistoricalMemoryPage = {
  items: HistoricalMemoryItem[];
  total: number;
  limit: number;
  offset: number;
  partitions: Array<{ key: string; label: string; count: number }>;
  sources: Array<{ key: string; label: string; count: number }>;
};

// U2 user-understanding labels. These are scoped, possibly-wrong views of the
// user; `body` is never a confirmed fact and must be presented as tentative.
export type UnderstandingLabel = {
  id: string;
  category: string;
  scope_key: string;
  canonical_key: string;
  body: string;
  state: string;
  grade: "low" | "medium" | "high";
  revision: number;
  created_at: string;
  updated_at: string;
};

export type UnderstandingPage = {
  items: UnderstandingLabel[];
  total: number;
  limit: number;
  offset: number;
  policy_epoch: number;
};

export type UnderstandingDetail = {
  label: UnderstandingLabel;
  evidence: Array<{
    evidence_ref: string;
    event_group: string;
    relation: "support" | "counter";
    source_revision: string;
    source_status: "recorded_unverified" | "available" | "unavailable";
  }>;
  versions: Array<{ revision: number; state: string; grade: string; actor: string; created_at: string }>;
};

// Must match memory.distillation.understanding.namespace in the gateway config.
const UNDERSTANDING_NAMESPACE = "general";

const understandingScope = (lane: string, namespace: string) => {
  const params = new URLSearchParams({ lane, namespace });
  return params;
};

export const fetchUnderstanding = (lane: string, namespace = UNDERSTANDING_NAMESPACE, offset = 0) => {
  const params = understandingScope(lane, namespace);
  params.set("limit", "50");
  params.set("offset", String(offset));
  return requestJson<UnderstandingPage>(`/api/companion/understanding?${params}`);
};

export const fetchUnderstandingDetail = (id: string, lane: string, namespace = UNDERSTANDING_NAMESPACE) =>
  requestJson<UnderstandingDetail>(
    `/api/companion/understanding/${encodeURIComponent(id)}?${understandingScope(lane, namespace)}`,
  );

export const updateUnderstanding = (id: string, lane: string, body: string, namespace = UNDERSTANDING_NAMESPACE) =>
  requestJson<{ success: true; policy_epoch: number; actor: "user_edit" }>(
    `/api/companion/understanding/${encodeURIComponent(id)}?${understandingScope(lane, namespace)}`,
    { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ body }) },
  );

export const actOnUnderstanding = (
  id: string, lane: string, action: "suppress" | "restore" | "forget", namespace = UNDERSTANDING_NAMESPACE,
) => requestJson<{ success: true; policy_epoch: number; action: string }>(
  `/api/companion/understanding/${encodeURIComponent(id)}/action?${understandingScope(lane, namespace)}`,
  { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action }) },
);

export type DiaryEntry = {
  id: string;
  author: "user" | "assistant";
  entry_date: string;
  content: string;
  created_at: string;
  updated_at: string;
  allow_ai_view: boolean;
  allow_memory: boolean;
  deleted_at: string | null;
};

export type DiaryAutomationStatus = {
  entry_date: string;
  status: "idle" | "pending" | "completed" | "failed";
  started_at: string | null;
  completed_at: string | null;
  assistant_entry_id: string | null;
  error: string;
  user_read_at: string | null;
  user_read_count: number;
  next_generation_at: string;
};

export type DiaryMemoryProgress = {
  diary_dates: number;
  diary_units: number;
  trigger_units: number;
};

export type RecentChapter = {
  id: string;
  title: string;
  summary: string;
  source_session_id: string;
  source_message_ids: number[];
  created_at: string;
  unavailable_source_count?: number;
};

export type HistoryItem = {
  id: string;
  title: string;
  preview: string;
  message_count: number;
  is_current: boolean;
  started_at?: string | null;
  last_active?: string | null;
};

export type CompanionBootstrap = {
  profile: { name?: string; status?: string };
  profile_details: {
    companion_name?: string;
    personality?: string;
    speaking_style?: string;
    user_nickname?: string;
    relationship?: string;
    boundaries?: string;
  };
  session_id: string;
  session_key: string;
  messages: ChatMessage[];
  timeline?: TimelineState;
  memories: MemoryItem[];
  recent_chapters: RecentChapter[];
  history: HistoryItem[];
  settings: {
    memory_location?: string;
    conversation_model?: string;
    distillation_model?: string;
    // Resolved by the gateway from memory.distillation.understanding.namespace.
    understanding_namespace?: string;
  };
};

export type EditableCompanionSettings = {
  model: {
    provider: string;
    model: string;
    base_url: string;
    api_key_configured: boolean;
  };
  channels: {
    feishu: { configured: boolean; app_id: string; app_secret_configured: boolean; restart_required: boolean };
    weixin: { configured: boolean; account_id: string; token_configured: boolean; setup_command?: string; restart_required: boolean };
  };
};

export type CompanionSettings = { settings: EditableCompanionSettings };

export type CompanionChannelLink = {
  link_id: string;
  platform: "weixin" | "feishu";
  status: "waiting" | "scanned" | "connected" | "expired" | "denied" | "error";
  qr_url?: string;
  qr_image?: string;
  expires_in?: number;
  restart_required?: boolean;
};

export const fetchCompanionBootstrap = (signal?: AbortSignal) =>
  requestJson<CompanionBootstrap>("/api/companion/bootstrap", { signal });

export const fetchCompanionSettings = () =>
  requestJson<CompanionSettings>("/api/companion/settings");

export const discoverCompanionModels = (options: { provider: string; base_url: string; api_key?: string }) =>
  requestJson<{ models: string[] }>("/api/companion/settings/models", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });

export const saveCompanionModel = (options: { provider: string; base_url: string; model: string; api_key?: string }) =>
  requestJson<{ success: true; settings: EditableCompanionSettings }>("/api/companion/settings/model", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });

export const startCompanionChannelLink = (platform: "weixin" | "feishu") =>
  requestJson<CompanionChannelLink>(`/api/companion/channels/${platform}/link`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });

export const fetchCompanionChannelLink = (linkId: string) =>
  requestJson<CompanionChannelLink>(`/api/companion/channels/link/${encodeURIComponent(linkId)}`);

export const restartCompanion = () =>
  requestJson<{ accepted: true }>("/api/companion/restart", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });

export const openCompanionProject = (path: string) =>
  requestJson<{ opened: true }>("/api/companion/projects/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });

export async function companionIsReady(): Promise<boolean> {
  try {
    const response = await fetch(apiPath("/health"), {
      cache: "no-store",
      credentials: "same-origin",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function waitForCompanionReady(options: {
  attempts?: number;
  delayMs?: number;
  initialDelayMs?: number;
} = {}): Promise<boolean> {
  const attempts = Math.max(1, options.attempts ?? 45);
  const delayMs = Math.max(100, options.delayMs ?? 1000);
  const initialDelayMs = Math.max(0, options.initialDelayMs ?? 2500);
  if (initialDelayMs) {
    await new Promise((resolve) => window.setTimeout(resolve, initialDelayMs));
  }
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (await companionIsReady()) return true;
    if (attempt + 1 < attempts) {
      await new Promise((resolve) => window.setTimeout(resolve, delayMs));
    }
  }
  return false;
}

export const fetchHistoricalMemory = (memoryId: string) =>
  requestJson<{ item: HistoricalMemoryDetail }>(`/api/memory/library/${encodeURIComponent(memoryId)}`);

export const updateHistoricalMemory = (memoryId: string, summary: string) =>
  requestJson<{ item: HistoricalMemoryDetail }>(`/api/memory/library/${encodeURIComponent(memoryId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ summary }),
  });

export const deleteHistoricalMemory = (memoryId: string) =>
  requestJson<{ item: HistoricalMemoryDetail }>(`/api/memory/library/${encodeURIComponent(memoryId)}`, { method: "DELETE" });

export const restoreHistoricalMemory = (memoryId: string) =>
  requestJson<{ item: HistoricalMemoryDetail }>(`/api/memory/library/${encodeURIComponent(memoryId)}/restore`, { method: "POST" });

export const permanentlyDeleteHistoricalMemory = (memoryId: string) =>
  requestJson<{ id: string; deleted: true; source_system: string; reason: string }>(
    `/api/memory/trash/${encodeURIComponent(memoryId)}/permanent`,
    {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation: "PERMANENT_DELETE" }),
    },
  );

export const fetchHistoricalTrash = (options: { limit?: number; offset?: number } = {}) => {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 50));
  params.set("offset", String(options.offset ?? 0));
  return requestJson<HistoricalMemoryPage>(`/api/memory/trash?${params.toString()}`);
};

export const fetchHistoricalMemories = (options: {
  source?: string;
  partition?: string;
  q?: string;
  limit?: number;
  offset?: number;
} = {}) => {
  const params = new URLSearchParams();
  if (options.source) params.set("source", options.source);
  if (options.partition) params.set("partition", options.partition);
  if (options.q) params.set("q", options.q);
  params.set("limit", String(options.limit ?? 50));
  params.set("offset", String(options.offset ?? 0));
  return requestJson<HistoricalMemoryPage>(`/api/memory/library?${params.toString()}`);
};

export const updateCompanionMemory = (memoryId: string, action: "resolve" | "forget" | "edit", content?: string) =>
  requestJson<{ success: true; id: string; action: string }>(
    `/api/companion/memories/${encodeURIComponent(memoryId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, content }),
    },
  );

export const startNewCompanionConversation = () =>
  requestJson<{ success: true; session_id: string; session_key: string }>("/api/companion/new", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });

export type CompanionConversation = {
  success: true;
  session_id: string;
  session_key: string;
  messages: ChatMessage[];
  timeline?: TimelineState;
  history: HistoryItem[];
};

export const switchCompanionConversation = (sessionId: string) =>
  requestJson<CompanionConversation>(
    `/api/companion/sessions/${encodeURIComponent(sessionId)}/switch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  );

export const rollbackCompanionTimeline = (
  sessionId: string,
  sessionKey: string,
  targetMessageId: number,
  preserveTarget = false,
) => requestJson<{
  success: true;
  session_id: string;
  target: ChatMessage;
  messages: ChatMessage[];
  rewound_count: number;
  timeline: TimelineState;
}>(`/api/sessions/${encodeURIComponent(sessionId)}/timeline/rollback`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-HoneyOS-Session-Key": sessionKey },
  body: JSON.stringify({ target_message_id: targetMessageId, preserve_target: preserveTarget }),
});

export const deleteCompanionConversation = (sessionId: string) =>
  requestJson<{ object: string; id: string; deleted: boolean }>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );

export const updateCompanionProfile = (profile: CompanionProfileDetails) =>
  requestJson<{ success: true; profile: CompanionProfileDetails }>("/api/companion/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });

export const getCompanionAvatarStatus = () =>
  requestJson<{ exists: boolean; version: string }>("/api/companion/avatar/status");

export const companionAvatarUrl = (version = "current") =>
  `${apiPath("/api/companion/avatar")}?v=${encodeURIComponent(version)}`;

export const updateCompanionAvatar = (dataUrl: string) =>
  requestJson<{ success: true; version: string }>("/api/companion/avatar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ data_url: dataUrl }),
  });

export const deleteCompanionAvatar = () =>
  requestJson<{ success: true }>("/api/companion/avatar", { method: "DELETE" });

export const fetchCompanionDiary = () =>
  requestJson<{
    entries: DiaryEntry[];
    trash: DiaryEntry[];
    trash_retention_days: number;
    automation: DiaryAutomationStatus;
    memory_progress: DiaryMemoryProgress;
  }>("/api/companion/diary");

export const retryCompanionDiary = (entryDate: string) =>
  requestJson<{ accepted: true; entry_date: string }>("/api/companion/diary/retry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ entry_date: entryDate }),
  });

export const createCompanionDiaryEntry = (entry: {
  entry_date: string;
  content: string;
  allow_ai_view: boolean;
  allow_memory: boolean;
}) =>
  requestJson<{ entry: DiaryEntry }>("/api/companion/diary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });

export const updateCompanionDiaryEntry = (
  entryId: string,
  changes: Partial<Pick<DiaryEntry, "content" | "allow_ai_view" | "allow_memory">>,
) =>
  requestJson<{ entry: DiaryEntry }>(
    `/api/companion/diary/${encodeURIComponent(entryId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    },
  );

export const deleteCompanionDiaryEntry = (entryId: string) =>
  requestJson<{ success: true; id: string }>(
    `/api/companion/diary/${encodeURIComponent(entryId)}`,
    { method: "DELETE" },
  );

export const restoreCompanionDiaryEntry = (entryId: string) =>
  requestJson<{ entry: DiaryEntry }>(
    `/api/companion/diary/${encodeURIComponent(entryId)}/restore`,
    { method: "POST" },
  );

export const permanentlyDeleteCompanionDiaryEntry = (entryId: string) =>
  requestJson<{ success: true; id: string }>(
    `/api/companion/diary/${encodeURIComponent(entryId)}/permanent`,
    { method: "DELETE" },
  );
