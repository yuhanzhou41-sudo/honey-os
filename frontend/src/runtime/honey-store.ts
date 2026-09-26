import { create } from "zustand";

import type { ChatMessage, CompanionBootstrap, CompanionProfileDetails, HistoryItem, MemoryItem, RecentChapter } from "../api/companion";
import { initialRunState, type HoneyEvent, type HoneyRunState } from "./honey-events";
import { reduceHoneyRun } from "./run-reducer";

type HoneyRuntimeState = {
  loading: boolean;
  error: string | null;
  sessionId: string | null;
  sessionKey: string | null;
  name: string;
  status: string;
  messages: ChatMessage[];
  memories: MemoryItem[];
  recentChapters: RecentChapter[];
  history: HistoryItem[];
  profile: CompanionBootstrap["profile_details"];
  summarySettings: CompanionBootstrap["settings"];
  run: HoneyRunState;
  sending: boolean;
  sendError: string | null;
  hydrate: (data: CompanionBootstrap) => void;
  fail: (message: string) => void;
  queueUserMessage: (message: string) => void;
  beginReply: () => void;
  beginTurn: (message: string) => void;
  applyRunEvent: (event: HoneyEvent) => void;
  finishTurn: () => void;
  finishStoppedTurn: () => void;
  finishStoppedEmpty: () => void;
  removeLastAssistantMessage: () => void;
  replaceTimelineMessages: (messages: ChatMessage[]) => void;
  mergeTimelineMessages: (messages: ChatMessage[]) => void;
  rollbackLocalMessages: (messageIndex: number) => void;
  failTurn: (message: string) => void;
  updateProfile: (profile: CompanionProfileDetails) => void;
  replaceMemories: (memories: MemoryItem[]) => void;
  replaceRecentChapters: (chapters: RecentChapter[]) => void;
  removeMemory: (memoryId: string) => void;
  startConversation: (sessionId: string, sessionKey: string) => void;
  switchConversation: (data: Pick<CompanionBootstrap, "session_id" | "session_key" | "messages" | "history">) => void;
  removeHistory: (sessionId: string) => void;
};

export const useHoneyStore = create<HoneyRuntimeState>((set) => ({
  loading: true,
  error: null,
  sessionId: null,
  sessionKey: null,
  name: "",
  status: "在这儿",
  messages: [],
  memories: [],
  recentChapters: [],
  history: [],
  profile: {},
  summarySettings: {},
  run: initialRunState,
  sending: false,
  sendError: null,
  hydrate: (data) =>
    set({
      loading: false,
      error: null,
      sessionId: data.session_id,
      sessionKey: data.session_key,
      name: data.profile.name || data.profile_details.companion_name || "",
      status: data.profile.status || "在这儿",
      messages: data.messages || [],
      memories: data.memories || [],
      recentChapters: data.recent_chapters || [],
      history: data.history || [],
      profile: data.profile_details || {},
      summarySettings: data.settings || {},
    }),
  fail: (message) => set({ loading: false, error: message }),
  queueUserMessage: (message) => set((state) => {
    const content = String(message || "").trim();
    if (!content || state.sending) return state;
    const priorReply = state.run.parts
      .filter((part) => part.kind === "text")
      .map((part) => part.content)
      .filter(Boolean)
      .join("\n\n") || state.run.content;
    const messages = state.run.phase === "completed" && priorReply
      ? [
          ...state.messages,
          { role: "assistant" as const, content: priorReply },
          { role: "user" as const, content },
        ]
      : [...state.messages, { role: "user" as const, content }];
    return {
      messages,
      run: initialRunState,
      sendError: null,
    };
  }),
  beginReply: () => set({
    run: { ...initialRunState, phase: "present" },
    sending: true,
    sendError: null,
  }),
  beginTurn: (message) => set((state) => {
    const priorReply = state.run.parts
      .filter((part) => part.kind === "text")
      .map((part) => part.content)
      .filter(Boolean)
      .join("\n\n") || state.run.content;
    const committed = state.run.phase === "completed" && priorReply
      ? [...state.messages, { role: "assistant" as const, content: priorReply }]
      : state.messages;
    const last = committed.at(-1);
    const messages = state.run.phase === "failed" && last?.role === "user" && last.content === message
      ? committed
      : [...committed, { role: "user" as const, content: message }];
    return {
      messages,
      run: { ...initialRunState, phase: "present" },
      sending: true,
      sendError: null,
    };
  }),
  applyRunEvent: (event) => set((state) => ({ run: reduceHoneyRun(state.run, event) })),
  finishTurn: () => set((state) => {
    const reply = state.run.parts
      .filter((part) => part.kind === "text")
      .map((part) => part.content)
      .filter(Boolean)
      .join("\n\n") || state.run.content;
    return {
      messages: reply
        ? [...state.messages, { role: "assistant" as const, content: reply }]
        : state.messages,
      run: reply ? initialRunState : state.run,
      sending: false,
    };
  }),
  finishStoppedTurn: () => set((state) => {
    const reply = state.run.parts
      .filter((part) => part.kind === "text")
      .map((part) => part.content)
      .filter(Boolean)
      .join("\n\n") || state.run.content;
    return {
      messages: reply
        ? [...state.messages, { role: "assistant" as const, content: reply }]
        : state.messages,
      run: initialRunState,
      sending: false,
      sendError: null,
    };
  }),
  finishStoppedEmpty: () => set({
    run: initialRunState,
    sending: false,
    sendError: null,
  }),
  removeLastAssistantMessage: () => set((state) => {
    const last = state.messages.at(-1);
    return last?.role === "assistant"
      ? { messages: state.messages.slice(0, -1), run: initialRunState, sendError: null }
      : state;
  }),
  replaceTimelineMessages: (messages) => set({
    messages,
    run: initialRunState,
    sending: false,
    sendError: null,
  }),
  mergeTimelineMessages: (incoming) => set((state) => {
    if (!incoming.length) return state;
    const knownIds = new Set(
      state.messages.map((message) => message.id).filter((id): id is number => typeof id === "number"),
    );
    const additions = incoming.filter(
      (message) => typeof message.id === "number" && !knownIds.has(message.id),
    );
    return additions.length ? { messages: [...state.messages, ...additions] } : state;
  }),
  rollbackLocalMessages: (messageIndex) => set((state) => ({
    messages: state.messages.slice(0, Math.max(0, messageIndex)),
    run: initialRunState,
    sendError: null,
  })),
  failTurn: (message) => set((state) => ({
    sending: false,
    sendError: message,
    run: reduceHoneyRun(state.run, { name: "error", payload: { message } }),
  })),
  updateProfile: (profile) => set({
    profile,
    name: profile.companion_name || "",
  }),
  replaceMemories: (memories) => set({ memories }),
  replaceRecentChapters: (recentChapters) => set({ recentChapters }),
  removeMemory: (memoryId) => set((state) => ({
    memories: state.memories.filter((memory) => memory.id !== memoryId),
  })),
  startConversation: (sessionId, sessionKey) => set((state) => ({
    sessionId,
    sessionKey,
    messages: [],
    history: [
      {
        id: sessionId,
        title: "",
        preview: "",
        message_count: 0,
        is_current: true,
        started_at: new Date().toISOString(),
        last_active: new Date().toISOString(),
      },
      ...state.history.map((item) => ({ ...item, is_current: false })),
    ],
    run: initialRunState,
    sending: false,
    sendError: null,
  })),
  switchConversation: (data) => set({
    sessionId: data.session_id,
    sessionKey: data.session_key,
    messages: data.messages || [],
    history: data.history || [],
    run: initialRunState,
    sending: false,
    sendError: null,
  }),
  removeHistory: (sessionId) => set((state) => ({
    history: state.history.filter((item) => item.id !== sessionId),
  })),
}));
