import StudyPlanDraft, { splitStudyPlanDraft } from "./StudyPlanDraft";
import { ArrowClockwiseIcon, ArrowDownIcon, ArrowUpIcon, ClockCounterClockwiseIcon, ImageIcon, PaperPlaneTiltIcon, PlusIcon, StopIcon, TrashIcon, XIcon, SmileyIcon } from "@phosphor-icons/react";
import { fetchStickerStatus, markStickerUsed, stickerChatMessage, type StickerItem, type StickerStatus } from "../../api/stickers";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  answerApproval,
  ChatRequestError,
  fetchChatRunStatus,
  naturalReplyInstructions,
  splitUserMessages,
  stopChat,
  streamChat,
  watchSessionMessages,
  userMessageBreak,
  fetchChatSessionModel,
  setChatSessionModel,
  type ChatInput,
  type ChatRunStatus,
} from "../../api/chat";
import { fetchModelOptions, type ModelOptions } from "../../api/models";
import { referenceChatStudyDocument, studyDocumentMarker } from "../../api/chat-study-library";
import type { StudyResource } from "../../api/study";
import { deleteCompanionConversation, fetchCompanionMessages, rollbackCompanionTimeline, startNewCompanionConversation, switchCompanionConversation, type ChatMessage, type HistoryItem } from "../../api/companion";
import { HoneyAvatar } from "../../components/honey/HoneyAvatar";
import { HoneyMessage } from "../../components/honey/HoneyMessage";
import { StickerDrawer } from "../../components/honey/StickerDrawer";
import { ErrorState, LoadingState } from "../../components/honey/PageState";
import { Button } from "../../components/ui/Button";
import type { HoneyEvent, PermissionChoice } from "../../runtime/honey-events";
import { requestJson } from "../../api/client";
import { assistantBubblesForDisplay } from "../../runtime/chat-bubble-segmenter";
import { useHoneyStore } from "../../runtime/honey-store";
import { HoneyRun } from "./HoneyRun";
import { ReplyFeedback } from "./ReplyFeedback";

type ChatAttachment = { id: string; name: string; dataUrl: string };
type QueuedMessage = { id: string; display: string; input: ChatInput };
type WorkMode = { enabled: boolean; work_id: string | null; session_id: string | null };
type WorkQuestion = { id: string; runId: string; text: string; choices: string[] };

const draftKey = (sessionId: string) => `honeyos-chat-draft:${sessionId}`;
const queueKey = (sessionId: string) => `honeyos-chat-pending:${sessionId}`;

function historicalImageUrls(content: string): string[] {
  return Array.from(
    content.matchAll(/^!\[[^\r\n]*?\]\((data:image\/[\w.+-]+;base64,[A-Za-z0-9+/=]+)\)\r?$/gm),
    (match) => match[1],
  ).slice(0, 4);
}

function historyTime(item: HistoryItem, field: "last_active" | "started_at") {
  const value = Date.parse(String(item[field] || ""));
  return Number.isFinite(value) ? value : 0;
}

function sortHistory(items: HistoryItem[]) {
  return [...items].sort((left, right) => {
    if (left.is_current !== right.is_current) return left.is_current ? -1 : 1;
    return historyTime(right, "last_active") - historyTime(left, "last_active")
      || historyTime(right, "started_at") - historyTime(left, "started_at")
      || left.id.localeCompare(right.id);
  });
}

function AssistantTurn({
  name,
  children,
  live = false,
  compact = false,
}: {
  name: string;
  children: ReactNode;
  live?: boolean;
  compact?: boolean;
}) {
  return (
    <article className="flex w-full items-start gap-3 text-[15px] leading-7" aria-live={live ? "polite" : undefined}>
      <HoneyAvatar name={name} className="mt-1 size-8 rounded-full text-xs" />
      <div
        className={[
          "min-w-0 rounded-[var(--radius-lg)] border border-[var(--border)]",
          "bg-[var(--surface-raised)] px-4 py-3 shadow-[0_8px_24px_rgba(56,48,39,0.05)]",
          compact
            ? "w-fit max-w-[85%] sm:max-w-[78%]"
            : "flex-1",
        ].join(" ")}
      >
        {children}
      </div>
    </article>
  );
}

function readChatImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/") || file.size > 15_000_000) {
      reject(new Error("image_invalid"));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("image_unreadable"));
    reader.onload = () => {
      const image = new Image();
      image.onerror = () => reject(new Error("image_unreadable"));
      image.onload = () => {
        const maximum = 1024;
        const scale = Math.min(1, maximum / Math.max(image.width, image.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(image.width * scale));
        canvas.height = Math.max(1, Math.round(image.height * scale));
        const context = canvas.getContext("2d");
        if (!context) return reject(new Error("image_unreadable"));
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL("image/jpeg", 0.8));
      };
      image.src = String(reader.result || "");
    };
    reader.readAsDataURL(file);
  });
}

function combineQueuedInputs(messages: QueuedMessage[]): ChatInput {
  const parts: Exclude<ChatInput, string> = [];
  messages.forEach((message, index) => {
    if (index) parts.push({ type: "text", text: userMessageBreak });
    if (typeof message.input === "string") {
      parts.push({ type: "text", text: message.input });
    } else {
      parts.push(...message.input);
    }
  });
  return parts;
}

export function ChatPage() {
  const queryClient = useQueryClient();
  const work = useQuery({
    queryKey: ["companion-work"],
    queryFn: () => requestJson<WorkMode>("/api/companion/work"),
    refetchOnWindowFocus: true,
  });
  const switchWork = useMutation({
    mutationFn: ({ enabled, sessionId }: { enabled: boolean; sessionId: string }) =>
      requestJson<WorkMode>("/api/companion/work", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled, session_id: sessionId }),
      }),
    onSuccess: (state) => queryClient.setQueryData(["companion-work"], state),
  });
  const [workQuestion, setWorkQuestion] = useState<WorkQuestion>();
  const [workAnswer, setWorkAnswer] = useState("");
  const answerWork = useMutation({
    mutationFn: async ({ question, answer }: { question: WorkQuestion; answer: string }) =>
      requestJson<{ answered: boolean }>("/api/companion/work/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: question.runId, question_id: question.id, answer }),
      }),
    onSuccess: () => setWorkQuestion(undefined),
  });

  function handleWorkEvent(event: HoneyEvent) {
    if (event.name === "work.question") {
      setWorkAnswer("");
      setWorkQuestion({
        id: String(event.payload.question_id),
        runId: String(event.payload.run_id),
        text: String(event.payload.question),
        choices: Array.isArray(event.payload.choices) ? event.payload.choices.map(String) : [],
      });
    } else if (event.name === "work.question.closed") {
      setWorkQuestion((current) => current?.id === event.payload.question_id ? undefined : current);
    }
  }
  const {
    loading, error, messages, name, status, sessionId, sessionKey, run, sending, history,
    queueUserMessage, beginReply, applyRunEvent, finishTurn, finishStoppedTurn, finishStoppedEmpty,
    replaceTimelineMessages, mergeTimelineMessages, failTurn, startConversation,
    switchConversation, removeHistory, rollbackLocalMessages,
  } = useHoneyStore();
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [studyDocuments, setStudyDocuments] = useState<StudyResource[]>([]);
  const [documentOpen, setDocumentOpen] = useState(false);
  const [documentPath, setDocumentPath] = useState("");
  const [documentNotice, setDocumentNotice] = useState("");

  useEffect(() => {
    setStudyDocuments([]);
    setDocumentPath("");
    setDocumentNotice("");
    setDocumentOpen(false);
  }, [sessionId]);

  const documentReference = useMutation({
    mutationFn: ({ path }: { path: string; session: string }) => referenceChatStudyDocument(path),
    onSuccess: ({ resource, reused }, { session }) => {
      if (useHoneyStore.getState().sessionId !== session) return;
      setStudyDocuments((current) =>
        current.some(({ id }) => id === resource.id) ? current : [...current, resource],
      );
      setDocumentPath("");
      setDocumentNotice(reused ? "已引用资料库中的相同文档" : "已在资料库引用原文件");
    },
    onError: (error: Error, { session }) => {
      if (useHoneyStore.getState().sessionId === session) setDocumentNotice(error.message);
    },
  });

  function referenceDocument() {
    if (!documentPath.trim() || !sessionId || studyDocuments.length >= 4 || documentReference.isPending) return;
    setDocumentNotice("");
    documentReference.mutate({ path: documentPath, session: sessionId });
  }
  const [queuedMessages, setQueuedMessages] = useState<QueuedMessage[]>([]);
  const [documentScopeRequired, setDocumentScopeRequired] = useState(false);
  const [submittedMessages, setSubmittedMessages] = useState<QueuedMessage[]>([]);
  const [attachmentError, setAttachmentError] = useState("");
  const [approvalPending, setApprovalPending] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    void fetchStickerStatus()
      .then(setStickerStatus)
      .catch(() => undefined);
  }, []);

  const [stoppedReply, setStoppedReply] = useState(false);
  const [stoppedUserMessageId, setStoppedUserMessageId] = useState<number | null>(null);
  const [recoverRunId, setRecoverRunId] = useState<string | null>(null);
  const [retryUserMessageId, setRetryUserMessageId] = useState<number | null>(null);
  const [chatModelOptions, setChatModelOptions] = useState<ModelOptions | null>(null);
  const [chatModelSelection, setChatModelSelection] = useState("");
  const [chatModelBusy, setChatModelBusy] = useState(false);
  const [chatModelError, setChatModelError] = useState("");

  useEffect(() => {
    let cancelled = false;
    void fetchModelOptions()
      .then((payload) => {
        if (!cancelled) setChatModelOptions(payload);
      })
      .catch(() => {
        if (!cancelled) setChatModelError("模型列表暂时无法读取");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!sessionId || !sessionKey || !chatModelOptions) return;
    let cancelled = false;
    setChatModelError("");
    void fetchChatSessionModel({ sessionId, sessionKey })
      .then((session) => {
        if (cancelled) return;
        const model = String((session.modelProvider && session.model) || chatModelOptions.model || "");
        const preferredProvider = String(session.modelProvider || chatModelOptions.provider || "");
        const providers = chatModelOptions.providers.filter(
          (provider) => provider.authenticated && provider.models.includes(model),
        );
        const preferred = providers.find((item) => item.slug === preferredProvider);
        const provider = session.modelProvider
          ? preferred
          : preferred || providers.find((item) => item.is_current) || providers[0];
        setChatModelSelection(
          provider && model ? `${provider.slug}::${model}` : "",
        );
      })
      .catch(() => {
        if (!cancelled) setChatModelError("当前会话模型状态暂时无法读取");
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, sessionKey, chatModelOptions]);

  async function handleChatModelChange(value: string) {
    if (!sessionId || !sessionKey || !value || sending || chatModelBusy) return;
    const splitAt = value.indexOf("::");
    if (splitAt <= 0) return;
    const provider = value.slice(0, splitAt);
    const model = value.slice(splitAt + 2);
    if (!provider || !model) return;

    const previous = chatModelSelection;
    setChatModelSelection(value);
    setChatModelBusy(true);
    setChatModelError("");
    try {
      await setChatSessionModel({ sessionId, sessionKey, provider, model });
    } catch (modelError) {
      setChatModelSelection(previous);
      setChatModelError(
        modelError instanceof Error ? modelError.message : "模型切换失败",
      );
    } finally {
      setChatModelBusy(false);
    }
  }

  const authenticatedChatModelProviders = (chatModelOptions?.providers || [])
    .filter((provider) => provider.authenticated && provider.models.length > 0);
  const [timelineError, setTimelineError] = useState("");
  const [stickerOpen, setStickerOpen] = useState(false);
  const [stickerStatus, setStickerStatus] = useState<StickerStatus | null>(null);
  const [activeMessageActions, setActiveMessageActions] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const followRef = useRef(true);
  const draftSessionRef = useRef<string | null>(null);
  const skipDraftWriteRef = useRef(false);
  const newConversation = useMutation({
    mutationFn: startNewCompanionConversation,
    onSuccess: (data) => {
      setQueuedMessages([]);
      setSubmittedMessages([]);
      startConversation(data.session_id, data.session_key);
    },
  });
  const switchConversationMutation = useMutation({
    mutationFn: switchCompanionConversation,
    onSuccess: (data) => {
      setQueuedMessages([]);
      setSubmittedMessages([]);
      switchConversation(data);
      setHistoryOpen(false);
      setHistoryError("");
    },
    onError: () => setHistoryError("刚才没有切换成功，请再试一次"),
  });
  const deleteConversationMutation = useMutation({
    mutationFn: deleteCompanionConversation,
    onSuccess: (data) => {
      if (data.deleted) removeHistory(data.id);
      setHistoryError("");
    },
    onError: () => setHistoryError("刚才没有删除成功，请再试一次"),
  });

  useEffect(() => {
    const viewport = scrollRef.current;
    if (viewport && followRef.current) {
      viewport.scrollTop = viewport.scrollHeight;
      setShowScrollButton(false);
    }
  }, [messages, run]);

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    if (!sessionId) return;
    const controller = new AbortController();
    let closed = false;
    let retryTimer: number | null = null;

    const listen = async () => {
      if (closed) return;
      try {
        await watchSessionMessages({
          sessionId,
          sessionKey: sessionKey ?? undefined,
          signal: controller.signal,
          onMessage: async (notice) => {
            if (closed || String(notice.session_id) !== String(sessionId)) return;
            try {
              const result = await fetchCompanionMessages(sessionId, sessionKey || "");
              if (!closed) mergeTimelineMessages(result.data || []);
            } catch {
              // Durable DB state remains authoritative; normal reopen can reconcile.
            }
          },
        });
      } catch {
        if (closed || controller.signal.aborted) return;
      }
      if (!closed) retryTimer = window.setTimeout(() => void listen(), 3000);
    };

    void listen();
    return () => {
      closed = true;
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
    };
  }, [sessionId, sessionKey, mergeTimelineMessages]);


  useEffect(() => {
    if (!sessionId || draftSessionRef.current === sessionId) return;
    if (draftSessionRef.current) {
      localStorage.setItem(draftKey(draftSessionRef.current), draft);
    }
    draftSessionRef.current = sessionId;
    skipDraftWriteRef.current = true;
    setDraft(localStorage.getItem(draftKey(sessionId)) || "");
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId || draftSessionRef.current !== sessionId) return;
    if (skipDraftWriteRef.current) {
      skipDraftWriteRef.current = false;
      return;
    }
    if (draft) localStorage.setItem(draftKey(sessionId), draft);
    else localStorage.removeItem(draftKey(sessionId));
  }, [draft, sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    try {
      const saved = JSON.parse(localStorage.getItem(queueKey(sessionId)) || "[]") as QueuedMessage[];
      const restored = Array.isArray(saved) ? saved : [];
      const current = useHoneyStore.getState().messages;
      const pending = restored.filter((item) => !current.some((message) =>
          message.role === "user"
          && splitUserMessages(message.content).some((part) => part === item.display),
        ));
      setQueuedMessages(pending);
      pending.forEach((item) => queueUserMessage(item.display));
      if (!pending.length) localStorage.removeItem(queueKey(sessionId));
    } catch {
      setQueuedMessages([]);
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    if (queuedMessages.length) localStorage.setItem(queueKey(sessionId), JSON.stringify(queuedMessages));
    else localStorage.removeItem(queueKey(sessionId));
  }, [queuedMessages, sessionId]);

  async function finishWithStatus(status: ChatRunStatus): Promise<boolean> {
    if (useHoneyStore.getState().sessionId !== sessionId) return true;
    if (status.content) {
      applyRunEvent({
        name: "assistant.completed",
        payload: { content: status.content, terminal_state: status.state, recovered: true },
      });
    }
    if (status.state === "completed") {
      const beforeSync = useHoneyStore.getState().run;
      let saved: ChatMessage[] = [];
      if (sessionId && sessionKey) {
        try {
          const timeline = await fetchCompanionMessages(sessionId, sessionKey, AbortSignal.timeout(2500));
          saved = timeline.data;
        } catch {
          // Keep the reply in the UI when the saved timeline cannot be fetched.
        }
      }
      const current = useHoneyStore.getState();
      if (current.sessionId !== sessionId || current.run !== beforeSync) return true;
      if (status.content && saved.at(-1)?.role === "assistant"
          && saved.at(-1)?.content.trim() === status.content.trim()) {
        replaceTimelineMessages(saved);
      } else {
        finishTurn();
      }
      setQueuedMessages([]);
      setSubmittedMessages([]);
      setRecoverRunId(null);
      setRetryUserMessageId(null);
      return true;
    }
    if (status.state === "stopped_partial") {
      finishStoppedTurn();
      setStoppedReply(true);
      setStoppedUserMessageId(Number(status.user_message_id || 0) || null);
      setRecoverRunId(null);
      setRetryUserMessageId(null);
      return true;
    }
    if (status.state === "stopped_empty") {
      finishStoppedEmpty();
      setSubmittedMessages([]);
      setStoppedReply(false);
      setStoppedUserMessageId(null);
      setRecoverRunId(null);
      setRetryUserMessageId(null);
      return true;
    }
    if (status.state === "empty_response") {
      failTurn("模型没有返回有效内容，可以重试这次回复");
      setRecoverRunId(null);
      setRetryUserMessageId(Number(status.user_message_id || 0) || null);
      return true;
    }
    if (status.state === "model_failed") {
      failTurn(status.error || "模型回复失败，可以重试");
      setRecoverRunId(null);
      setRetryUserMessageId(Number(status.user_message_id || 0) || null);
      return true;
    }
    if (status.state === "tool_failed") {
      failTurn(status.error || "工具执行失败，可以重试");
      setRecoverRunId(null);
      setRetryUserMessageId(Number(status.user_message_id || 0) || null);
      return true;
    }
    if (status.state === "cancel_failed") {
      failTurn("停止请求没有成功，请先查询当前回复状态");
      return true;
    }
    return false;
  }

  async function recoverInterruptedRun(runId: string) {
    if (!sessionId || !sessionKey) return;
    setRecoverRunId(runId);
    for (let attempt = 0; attempt < 20; attempt += 1) {
      try {
        const status = await fetchChatRunStatus({ sessionId, sessionKey, runId });
        if (await finishWithStatus(status)) return;
      } catch {
        break;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 300));
    }
    failTurn("连接中断，尚未取回原回复；重新连接不会重复发送你的消息");
  }

  async function generateReply(pending = queuedMessages) {
    if (!pending.length || sending || chatModelBusy || !sessionId || !sessionKey) return;
    const submitted = [...pending];
    setDocumentScopeRequired(false);
    followRef.current = true;
    setStoppedReply(false);
    setStoppedUserMessageId(null);
    setRecoverRunId(null);
    setRetryUserMessageId(null);
    setWorkQuestion(undefined);
    beginReply();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let terminalStatus: ChatRunStatus | null = null;
      await streamChat({
        sessionId,
        sessionKey,
        message: combineQueuedInputs(submitted),
        instructions: work.data?.enabled ? undefined : naturalReplyInstructions,
        signal: controller.signal,
        onEvent: (event) => {
          handleWorkEvent(event);
          if (event.name === "run.started") {
            setSubmittedMessages(submitted);
            setQueuedMessages([]);
          }
          if (event.name === "assistant.completed" && event.payload.terminal_state) {
            terminalStatus = {
              run_id: String(event.payload.run_id || ""),
              session_id: String(event.payload.session_id || sessionId),
              state: String(event.payload.terminal_state) as ChatRunStatus["state"],
              content: String(event.payload.content || ""),
              user_message_id: Number(event.payload.user_message_id || 0),
            };
          }
          applyRunEvent(event);
        },
      });
      if (terminalStatus && await finishWithStatus(terminalStatus)) return;
      finishTurn();
      setQueuedMessages([]);
      setSubmittedMessages([]);
    } catch (streamError) {
      if (controller.signal.aborted) {
        const stoppedRun = useHoneyStore.getState().run;
        const partialReply = stoppedRun.parts
          .filter((part) => part.kind === "text")
          .map((part) => part.content)
          .filter(Boolean)
          .join("\n\n") || stoppedRun.content;
        if (partialReply.trim()) {
          finishStoppedTurn();
          setStoppedReply(true);
        } else {
          failTurn("已停止这次回复");
        }
      } else {
        if (streamError instanceof ChatRequestError && streamError.code === "study_scope_required") {
          setDocumentScopeRequired(true);
        }
        const runId = useHoneyStore.getState().run.runId;
        if (runId) await recoverInterruptedRun(runId);
        else failTurn(streamError instanceof Error ? streamError.message : "connection_failed");
      }
    } finally {
      abortRef.current = null;
    }
  }

  function send(event: FormEvent) {
    event.preventDefault();
    if (sending || chatModelBusy || documentReference.isPending) return;
    const text = [
      draft.trim(),
      ...studyDocuments.map((resource) => studyDocumentMarker(resource.id, resource.title)),
    ].filter(Boolean).join("\n\n");
    if (!text && !attachments.length) return;
    const message = [text, ...attachments.map((item) => `![${item.name}](${item.dataUrl})`)].filter(Boolean).join("\n\n");
    const input: ChatInput = attachments.length ? [
      ...(text ? [{ type: "text" as const, text: text }] : []),
      ...attachments.map((item) => ({ type: "image_url" as const, image_url: { url: item.dataUrl, detail: "auto" as const } })),
    ] : text;

    setDraft("");
    if (sessionId) localStorage.removeItem(draftKey(sessionId));
    setAttachments([]);
    setStudyDocuments([]);
    setDocumentNotice("");
    setDocumentOpen(false);
    setAttachmentError("");
    setStoppedReply(false);
    queueUserMessage(message);
    setQueuedMessages((current) => [
      ...current,
      { id: `${Date.now()}-${Math.random()}`, display: message, input },
    ]);
  }

  async function stopOrFinishReply() {
    if (sending) {
      if (!sessionId || !sessionKey || !run.runId) {
        failTurn("停止请求尚未准备好，请稍后再试");
        return;
      }
      try {
        const status = await stopChat({ sessionId, sessionKey, runId: run.runId });
        if (status.state === "cancel_failed") await finishWithStatus(status);
      } catch {
        failTurn("停止请求失败；不会自动重新发送你的消息");
      }
      return;
    }
  }

  async function regenerateStoppedReply() {
    if (!stoppedReply || sending || !submittedMessages.length || !sessionId || !sessionKey) return;
    if (!stoppedUserMessageId) {
      setTimelineError("没有找到原用户轮次，不能安全地重新生成");
      return;
    }
    try {
      const data = await rollbackCompanionTimeline(
        sessionId,
        sessionKey,
        stoppedUserMessageId,
        true,
      );
      replaceTimelineMessages(data.messages);
      setStoppedReply(false);
      window.setTimeout(
        () => void generateReplyFrom(submittedMessages, stoppedUserMessageId),
        0,
      );
    } catch {
      setTimelineError("刚才没有清理已停止的回复，请再试一次");
    }
  }

  async function retryFailedReply() {
    if (!retryUserMessageId || !sessionId || !sessionKey || !submittedMessages.length) return;
    try {
      const data = await rollbackCompanionTimeline(
        sessionId,
        sessionKey,
        retryUserMessageId,
        true,
      );
      replaceTimelineMessages(data.messages);
      const target = retryUserMessageId;
      setRetryUserMessageId(null);
      window.setTimeout(() => void generateReplyFrom(submittedMessages, target), 0);
    } catch {
      setTimelineError("没有清理失败的回复，暂时不能安全重试");
    }
  }

  async function rollbackMessage(message: ChatMessage, mode: "delete" | "regenerate", partIndex = 0) {
    if (!sessionId || !sessionKey || !message.id || sending) return;
    const sourceIndex = messages.findIndex((item) => item.id === message.id);
    const preceding = mode === "regenerate"
      ? [...messages.slice(0, sourceIndex)].reverse().find((item) => item.role === "user" && item.id)
      : message;
    if (!preceding?.id) return;
    if (mode === "delete" && !window.confirm("这条消息以及它后面的聊天都会回滚。继续吗？")) return;
    setTimelineError("");
    try {
      const preserveTarget = mode === "regenerate";
      const data = await rollbackCompanionTimeline(
        sessionId,
        sessionKey,
        preceding.id,
        preserveTarget,
      );
      replaceTimelineMessages(data.messages);
      const userParts = splitUserMessages(preceding.content)
        .filter((_, index) => mode === "regenerate" || index !== partIndex);
      const restored = userParts.map((content, index) => ({
        id: `rollback-${Date.now()}-${index}`,
        display: content,
        input: content as ChatInput,
      }));
      setQueuedMessages(restored);
      setStoppedReply(false);
      if (mode === "regenerate" && restored.length) {
        window.setTimeout(() => void generateReplyFrom(restored, preceding.id), 0);
      }
    } catch (rollbackError) {
      const messageText = rollbackError instanceof Error ? rollbackError.message : "timeline_rollback_failed";
      setTimelineError(messageText === "timeline_locked"
        ? "这部分聊天已经进入记忆整理，不能再回滚"
        : messageText === "timeline_busy"
          ? "正在整理这部分记忆，请稍后再试"
          : "刚才没有回滚成功，请再试一次");
    }
  }

  async function generateReplyFrom(pending: QueuedMessage[], reuseUserMessageId?: number) {
    if (!pending.length || sending || !sessionId || !sessionKey) return;
    setQueuedMessages(pending);
    followRef.current = true;
    setWorkQuestion(undefined);
    beginReply();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let terminalStatus: ChatRunStatus | null = null;
      await streamChat({
        sessionId, sessionKey, message: combineQueuedInputs(pending),
        instructions: work.data?.enabled ? undefined : naturalReplyInstructions,
        reuseUserMessageId,
        signal: controller.signal,
        onEvent: (event) => {
          handleWorkEvent(event);
          if (event.name === "run.started") {
            setSubmittedMessages(pending);
            setQueuedMessages([]);
          }
          if (event.name === "assistant.completed" && event.payload.terminal_state) {
            terminalStatus = {
              run_id: String(event.payload.run_id || ""),
              session_id: String(event.payload.session_id || sessionId),
              state: String(event.payload.terminal_state) as ChatRunStatus["state"],
              content: String(event.payload.content || ""),
              user_message_id: Number(event.payload.user_message_id || reuseUserMessageId || 0),
            };
          }
          applyRunEvent(event);
        },
      });
      if (terminalStatus && await finishWithStatus(terminalStatus)) return;
      finishTurn();
      setQueuedMessages([]);
      setSubmittedMessages([]);
    } catch (streamError) {
      if (controller.signal.aborted) finishStoppedTurn();
      else {
        const runId = useHoneyStore.getState().run.runId;
        if (runId) await recoverInterruptedRun(runId);
        else failTurn(streamError instanceof Error ? streamError.message : "connection_failed");
      }
    } finally {
      abortRef.current = null;
    }
  }

  function rollbackLocalMessage(sourceIndex: number, partIndex: number, edit: boolean) {
    const source = messages[sourceIndex];
    if (!source || source.role !== "user") return;
    const parts = splitUserMessages(source.content);
    const selected = parts[partIndex] || source.content;
    const queueIndex = queuedMessages.findIndex((item) => item.display === selected);
    const nextQueue = queueIndex >= 0 ? queuedMessages.slice(0, queueIndex) : [];
    rollbackLocalMessages(sourceIndex);
    setQueuedMessages(nextQueue);
    if (edit) setDraft(selected);
  }

  async function attachFiles(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;

    setAttachmentError("");
    const imageFiles = files.filter((file) => file.type.startsWith("image/"));
    const documentFiles = files.filter((file) => !file.type.startsWith("image/"));

    try {
      if (imageFiles.length) {
        const allowedImages = imageFiles.slice(0, Math.max(0, 4 - attachments.length));
        const next = await Promise.all(allowedImages.map(async (file) => ({
          id: `${file.name}-${file.lastModified}-${file.size}`,
          name: file.name,
          dataUrl: await readChatImage(file),
        })));
        setAttachments((current) => [...current, ...next].slice(0, 4));
      }

      if (documentFiles.length) {
        setAttachmentError("学习资料请通过「引用本机文档」加入。");
      }
    } catch (error) {
      setAttachmentError(
        error instanceof Error
          ? `附件处理失败：${error.message}`
          : "附件处理失败，请确认文件格式和大小",
      );
    }
  }

  function reattachImage(id: string, dataUrl: string) {
    setAttachmentError("");
    setAttachments((current) => {
      if (current.length >= 4 || current.some((item) => item.dataUrl === dataUrl)) return current;
      return [...current, { id, dataUrl, name: "历史图片" }];
    });
  }

  function sendSticker(item: StickerItem) {
    if (sending) return;
    const message = stickerChatMessage(item);
    queueUserMessage(message);
    setQueuedMessages((current) => [
      ...current,
      { id: `${Date.now()}-${Math.random()}`, display: message, input: message },
    ]);
    setStickerOpen(false);
    void markStickerUsed(item.id).catch(() => undefined);
  }

  function createConversation() {
    if (sending || newConversation.isPending) return;
    if ((messages.length || queuedMessages.length) && !window.confirm("开启新的聊天？之前的内容和记忆仍会保留。")) return;
    if (sessionId) localStorage.removeItem(draftKey(sessionId));
    setDraft("");
    newConversation.mutate();
  }

  function openConversation(targetSessionId: string) {
    if (targetSessionId === sessionId || replyBusy || switchConversationMutation.isPending) return;
    switchConversationMutation.mutate(targetSessionId);
  }

  function deleteConversation(item: HistoryItem) {
    if (item.is_current || deleteConversationMutation.isPending) return;
    const label = item.title || item.preview || "这段历史聊天";
    if (!window.confirm(`删除“${label}”？已整理出的记忆不会删除。`)) return;
    localStorage.removeItem(draftKey(item.id));
    deleteConversationMutation.mutate(item.id);
  }

  async function respondToApproval(choice: PermissionChoice, approvalId: string) {
    if (!sessionId || !sessionKey || approvalPending) return;
    setApprovalPending(true);
    try {
      await answerApproval({ sessionId, sessionKey, choice, approvalId });
      applyRunEvent({ name: "approval.responded", payload: { choice, approval_id: approvalId } });
    } catch (approvalError) {
      failTurn(approvalError instanceof Error ? approvalError.message : "approval_unavailable");
    } finally {
      setApprovalPending(false);
    }
  }

  if (loading) return <div className="p-5 sm:p-8"><LoadingState /></div>;
  if (error) return <div className="grid min-h-[100dvh] place-items-center p-5"><ErrorState /></div>;

  const recentStart = Math.max(0, messages.length - 40);
  const recentMessages = messages.slice(recentStart);
  const visible = recentMessages.flatMap((message, messageIndex) => {
    const sourceIndex = recentStart + messageIndex;
    const previousUserText = message.role === "assistant"
      ? messages.slice(0, sourceIndex).reverse().find((item) => item.role === "user")?.content || ""
      : "";
    const parts = message.role === "assistant"
      ? (splitStudyPlanDraft(message.content).draft
        ? [message.content] : assistantBubblesForDisplay(message.content, previousUserText))
      : splitUserMessages(message.content);
    return parts.map((content, partIndex) => ({
      ...message,
      content,
      displayKey: `${message.role}-${messageIndex}-${partIndex}`,
      partIndex,
      lastPart: partIndex === parts.length - 1,
      sourceIndex,
    }));
  });
  const activeBubbleUserText = (submittedMessages.length ? submittedMessages : queuedMessages)
    .map((item) => item.display)
    .join(`\n${userMessageBreak}\n`);
  const liveAssistantText = run.parts
    .filter((part) => part.kind === "text")
    .map((part) => part.content)
    .filter(Boolean)
    .join("\n\n") || run.content;
  const liveAssistantBubbles = liveAssistantText.trim()
    ? assistantBubblesForDisplay(liveAssistantText, activeBubbleUserText)
    : [];
  const activityRun = {
    ...run,
    content: "",
    parts: run.parts.filter((part) => part.kind !== "text"),
  };
  const showActivityRun = run.phase !== "idle" && Boolean(
    activityRun.presence || activityRun.parts.length || run.phase === "failed"
  );
  const replyBusy = sending;
  return (
    <section className="relative flex h-full min-h-0 w-full flex-col bg-[var(--background)] px-3 sm:px-7">
      <header className="mx-auto flex min-h-[4.75rem] w-full max-w-[56rem] shrink-0 items-center gap-3 border-b border-[var(--border)] px-1">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold tracking-[-0.02em]">{name}</h1>
          <p className="truncate text-xs text-[var(--foreground-muted)]">{work.data?.enabled ? "工作模式" : replyBusy ? "正在陪你聊" : status}</p>
        </div>
        {work.data ? <Button type="button" variant="secondary" disabled={!sessionId || replyBusy || switchWork.isPending}
          onClick={() => sessionId && switchWork.mutate({ enabled: !work.data?.enabled, sessionId })}>
          {work.data.enabled ? "结束工作" : "开始工作"}
        </Button> : null}
        <Button className="ml-auto" type="button" size="icon" variant="ghost" aria-label="历史聊天" title="历史聊天" onClick={() => setHistoryOpen((open) => !open)}>
          <ClockCounterClockwiseIcon size={20} />
        </Button>
        {authenticatedChatModelProviders.length ? (
          <div className="flex shrink-0 flex-col items-end gap-1">
            <label className="sr-only" htmlFor="honeyos-chat-model">当前会话模型</label>
            <select
              id="honeyos-chat-model"
              aria-label="聊天模型"
              title="当前会话模型覆盖（优先于全局默认）"
              className="h-8 w-[6.75rem] max-w-[24vw] shrink-0 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-raised)] px-2 text-[11px] text-[var(--foreground)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:opacity-50 sm:w-[8.5rem]"
              value={chatModelSelection}
              disabled={sending || chatModelBusy || !sessionId || !sessionKey}
              onChange={(event) => void handleChatModelChange(event.target.value)}
            >
              {!chatModelSelection ? <option value="">选择模型</option> : null}
              {authenticatedChatModelProviders.map((provider) => (
                <optgroup key={provider.slug} label={provider.name}>
                  {provider.models.map((model) => (
                    <option key={`${provider.slug}::${model}`} value={`${provider.slug}::${model}`}>
                      {model}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {chatModelError ? (
              <span
                className="max-w-[14rem] truncate text-[10px] text-[var(--danger)]"
                title={chatModelError}
              >
                {chatModelError}
              </span>
            ) : null}
          </div>
        ) : null}
        <Button type="button" size="icon" variant="ghost" aria-label="开启新的聊天" title="开启新的聊天" disabled={replyBusy || newConversation.isPending} onClick={createConversation}>
          <PlusIcon size={20} />
        </Button>
        <Link
          to="/relationship"
          aria-label={`查看${name}的资料`}
          className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)]"
        >
          <HoneyAvatar name={name} className="size-10 rounded-full shadow-none" />
        </Link>
        {authenticatedChatModelProviders.length ? (
          <div className="flex shrink-0 flex-col items-end gap-1">
            <label className="sr-only" htmlFor="honeyos-chat-model">当前会话模型</label>
            <select
              id="honeyos-chat-model"
              aria-label="聊天模型"
              title="当前会话模型覆盖（优先于全局默认）"
              className="h-8 w-[6.75rem] max-w-[24vw] shrink-0 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-raised)] px-2 text-[11px] text-[var(--foreground)] outline-none focus-visible:ring-2 focus-visible:ring-[var(--focus)] disabled:opacity-50 sm:w-[8.5rem]"
              value={chatModelSelection}
              disabled={sending || chatModelBusy || !sessionId || !sessionKey}
              onChange={(event) => void handleChatModelChange(event.target.value)}
            >
              {!chatModelSelection ? <option value="">选择模型</option> : null}
              {authenticatedChatModelProviders.map((provider) => (
                <optgroup key={provider.slug} label={provider.name}>
                  {provider.models.map((model) => (
                    <option key={`${provider.slug}::${model}`} value={`${provider.slug}::${model}`}>
                      {model}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {chatModelError ? (
              <span
                className="max-w-[14rem] truncate text-[10px] text-[var(--danger)]"
                title={chatModelError}
              >
                {chatModelError}
              </span>
            ) : null}
          </div>
        ) : null}
      </header>
      {switchWork.error ? <p className="mx-auto my-2 w-full max-w-[56rem] text-sm" role="alert">{switchWork.error.message}</p> : null}
      {sending && workQuestion ? (
        <form className="mx-auto my-3 grid w-full max-w-[56rem] gap-2 rounded-xl border border-[var(--border)] p-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (workAnswer.trim()) answerWork.mutate({ question: workQuestion, answer: workAnswer.trim() });
          }}>
          <label htmlFor="work-answer" className="text-sm font-semibold">{workQuestion.text}</label>
          {workQuestion.choices.length ? <div className="flex flex-wrap gap-2">
            {workQuestion.choices.map((choice) => <Button type="button" variant="secondary" key={choice}
              disabled={answerWork.isPending} onClick={() => answerWork.mutate({ question: workQuestion, answer: choice })}>{choice}</Button>)}
          </div> : null}
          <div className="flex gap-2">
            <input id="work-answer" className="honey-setting-control min-w-0 flex-1" placeholder="输入回答"
              maxLength={2000} value={workAnswer} onChange={(event) => setWorkAnswer(event.target.value)} />
            <Button type="submit" disabled={answerWork.isPending || !workAnswer.trim()}>回答</Button>
          </div>
          {answerWork.error ? <p role="alert" className="text-sm">{answerWork.error.message}</p> : null}
        </form>
      ) : null}

      {historyOpen ? (
        <>
          <button type="button" className="absolute inset-0 z-20 bg-black/20 sm:hidden" aria-label="关闭历史聊天" onClick={() => setHistoryOpen(false)} />
          <aside className="absolute bottom-0 left-0 top-0 z-30 flex w-[min(22rem,88vw)] flex-col border-r border-[var(--border)] bg-[var(--surface-raised)] shadow-[16px_0_40px_rgba(56,48,39,0.12)]">
            <div className="flex min-h-[4.75rem] items-center border-b border-[var(--border)] px-4">
              <h2 className="font-semibold">历史聊天</h2>
              <Button className="ml-auto" type="button" size="icon" variant="ghost" aria-label="关闭历史聊天" onClick={() => setHistoryOpen(false)}><XIcon size={19} /></Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              {sortHistory(history).map((item) => (
                <div key={item.id} className={`group flex items-center gap-1 rounded-[var(--radius-md)] ${item.is_current ? "bg-[var(--surface-subtle)]" : "hover:bg-[var(--surface-subtle)]"}`}>
                  <button type="button" className="min-w-0 flex-1 px-3 py-3 text-left" disabled={item.is_current || replyBusy || switchConversationMutation.isPending} onClick={() => openConversation(item.id)}>
                    <span className="block truncate text-sm font-medium">{item.title || item.preview || "未命名聊天"}</span>
                    <span className="mt-1 block truncate text-xs text-[var(--foreground-muted)]">{item.is_current ? "当前聊天" : `${item.message_count} 条消息`}</span>
                  </button>
                  {!item.is_current ? (
                    <Button className="mr-1 shrink-0 opacity-70 group-hover:opacity-100" type="button" size="icon" variant="ghost" aria-label="删除历史聊天" title="删除历史聊天" onClick={() => deleteConversation(item)}><TrashIcon size={17} /></Button>
                  ) : null}
                </div>
              ))}
              {!history.length ? <p className="px-3 py-8 text-center text-sm text-[var(--foreground-muted)]">还没有历史聊天</p> : null}
              {historyError ? <p className="px-3 py-2 text-sm text-[var(--danger)]" role="alert">{historyError}</p> : null}
            </div>
          </aside>
        </>
      ) : null}

      <div className="relative min-h-0 flex-1">
        <div
          ref={scrollRef}
          className="h-full min-h-0 overflow-y-auto overscroll-contain px-1 py-6 sm:px-3"
          aria-label="对话"
          onScroll={(event) => {
            const node = event.currentTarget;
            const nearBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 120;
            followRef.current = nearBottom;
            setShowScrollButton(!nearBottom);
          }}
        >
          <div className="mx-auto flex min-h-full w-full max-w-[56rem] flex-col justify-end gap-5">
        {visible.length ? (
          visible.map((message) => (
            message.role === "assistant" ? (
              <AssistantTurn key={message.displayKey} name={name} compact>
                <div
                  className="relative outline-none"
                  tabIndex={message.timeline_editable && message.id ? 0 : undefined}
                  onClick={() => {
                    if (!message.timeline_editable || !message.id) return;
                    setActiveMessageActions((current) =>
                      current === message.displayKey ? null : message.displayKey
                    );
                  }}
                >
                  <StudyAssistantContent content={message.content} messageId={message.displayKey} />
                  {sessionId && sessionKey && message.id && message.lastPart ? (
                    <ReplyFeedback key={`${sessionId}:${message.id}`} sessionId={sessionId} sessionKey={sessionKey}
                      messageId={message.id} initial={message.feedback} />
                  ) : null}
                  {message.timeline_editable && message.id ? (
                    <div
                      className={[
                        "absolute right-0 top-full z-10 mt-1 flex items-center gap-1 rounded-md",
                        "border border-[var(--border)] bg-[var(--surface-raised)] p-1 shadow-sm transition-opacity",
                        activeMessageActions === message.displayKey
                          ? "pointer-events-auto opacity-100"
                          : "pointer-events-none opacity-0",
                      ].join(" ")}
                      onClick={(event) => event.stopPropagation()}
                    >
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        className="size-7 opacity-70 hover:opacity-100"
                        aria-label="重新生成这条回复"
                        title="重新生成"
                        onClick={() => void rollbackMessage(message, "regenerate")}
                      >
                        <ArrowClockwiseIcon size={14} />
                      </Button>
                    </div>
                  ) : null}
                </div>
              </AssistantTurn>
            ) : (
              <article key={message.displayKey} className="ml-auto flex max-w-[92%] items-start gap-2 text-[15px] leading-7 sm:max-w-[78%]">
                <div
                  className="relative min-w-0 rounded-[var(--radius-lg)] bg-[var(--surface-subtle)] px-4 py-3 outline-none"
                  tabIndex={message.timeline_editable || !message.id ? 0 : undefined}
                  onClick={() => {
                    if (!(message.timeline_editable || !message.id)) return;
                    setActiveMessageActions((current) =>
                      current === message.displayKey ? null : message.displayKey
                    );
                  }}
                >
                  <HoneyMessage
                    content={message.content}
                    plain={!message.content.includes("data:image/")}
                    role={message.role}
                    messageId={message.displayKey}
                  />
                  {historicalImageUrls(message.content).map((url, index) => (
                    <button
                      key={index}
                      type="button"
                      disabled={attachments.length >= 4 || attachments.some((item) => item.dataUrl === url)}
                      className="mr-2 text-xs text-[var(--foreground-muted)] underline disabled:opacity-50"
                      onClick={(event) => {
                        event.stopPropagation();
                        reattachImage(["history", message.displayKey, index].join("-"), url);
                      }}
                    >
                      重看图片 {index + 1}
                    </button>
                  ))}
                  {message.timeline_editable && message.id ? (
                    <div
                      className={[
                        "absolute right-1 top-full z-10 mt-1 flex items-center gap-1 rounded-md",
                        "border border-[var(--border)] bg-[var(--surface-raised)] p-1 shadow-sm transition-opacity",
                        activeMessageActions === message.displayKey
                          ? "pointer-events-auto opacity-100"
                          : "pointer-events-none opacity-0",
                      ].join(" ")}
                      onClick={(event) => event.stopPropagation()}
                    >
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        className="size-7 opacity-70 hover:opacity-100"
                        aria-label="删除并回滚后续聊天"
                        title="删除"
                        onClick={() => void rollbackMessage(message, "delete", message.partIndex)}
                      >
                        <TrashIcon size={14} />
                      </Button>
                    </div>
                  ) : !message.id ? (
                    <div
                      className={[
                        "absolute right-1 top-full z-10 mt-1 flex items-center gap-1 rounded-md",
                        "border border-[var(--border)] bg-[var(--surface-raised)] px-1 py-0.5 shadow-sm transition-opacity",
                        activeMessageActions === message.displayKey
                          ? "pointer-events-auto opacity-100"
                          : "pointer-events-none opacity-0",
                      ].join(" ")}
                      onClick={(event) => event.stopPropagation()}
                    >
                      <Button
                        type="button"
                        variant="ghost"
                        className="h-7 px-2 text-xs opacity-70 hover:opacity-100"
                        onClick={() => rollbackLocalMessage(message.sourceIndex, message.partIndex, true)}
                      >
                        编辑
                      </Button>
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        className="size-7 opacity-70 hover:opacity-100"
                        aria-label="删除这条待发送消息"
                        title="删除"
                        onClick={() => rollbackLocalMessage(message.sourceIndex, message.partIndex, false)}
                      >
                        <TrashIcon size={14} />
                      </Button>
                    </div>
                  ) : null}
                </div>
                <HoneyAvatar name="你" surface="user" className="mt-1 size-8 rounded-full text-xs" />
              </article>
            )
          ))
        ) : (
          <div className="max-w-md py-16 pl-11">
            <h2 className="text-2xl font-semibold tracking-[-0.025em]">我在这儿</h2>
            <p className="mt-2 leading-7 text-[var(--foreground-muted)]">想说什么都可以。</p>
          </div>
        )}
        {liveAssistantBubbles.map((content, index) => (
          <AssistantTurn
            key={`live-${run.runId || "reply"}-${index}`}
            name={name}
            live={index === liveAssistantBubbles.length - 1}
            compact
          >
            <HoneyMessage
              content={content}
              role="assistant"
              messageId={`live-${run.runId || "reply"}-${index}`}
              isStreaming={sending && index === liveAssistantBubbles.length - 1}
            />
          </AssistantTurn>
        ))}
        {showActivityRun ? (
          <AssistantTurn name={name} live>
            <HoneyRun
              run={activityRun}
              approvalPending={approvalPending}
              onAnswer={respondToApproval}
              onRetry={run.phase === "failed" && recoverRunId
                ? () => void recoverInterruptedRun(recoverRunId)
                : run.phase === "failed" && retryUserMessageId && submittedMessages.length
                  ? () => void retryFailedReply()
                  : undefined}
            />
          </AssistantTurn>
        ) : null}
          </div>
        </div>
        {showScrollButton ? (
          <Button
            type="button"
            size="icon"
            variant="secondary"
            className="absolute bottom-3 left-1/2 -translate-x-1/2 shadow-[0_8px_24px_rgba(56,48,39,0.12)]"
            aria-label="回到最新消息"
            onClick={() => {
              const node = scrollRef.current;
              if (!node) return;
              followRef.current = true;
              node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
              setShowScrollButton(false);
            }}
          >
            <ArrowDownIcon size={18} />
          </Button>
        ) : null}
      </div>

      <form className="relative mx-auto w-full max-w-[56rem] shrink-0 pb-[calc(14px+env(safe-area-inset-bottom))] pt-2" onSubmit={send}>
        {documentScopeRequired && queuedMessages.length > 0 && !replyBusy ? (
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="text-sm">可在下方输入范围，也可以让 Honey 帮你分批读取。</span>
            <Button type="button" variant="secondary" onClick={() => {
              const consent = "不清楚，自动分批读取";
              void generateReply([...queuedMessages, { id: `reading-${Date.now()}`, input: consent, display: consent }]);
            }}>不清楚，自动分批读取</Button>
          </div>
        ) : null}
        {stoppedReply && queuedMessages.length && !replyBusy ? (
          <div className="mb-2 flex justify-center">
            <Button type="button" variant="secondary" onClick={regenerateStoppedReply}>
              <ArrowClockwiseIcon size={16} />
              重新生成
            </Button>
          </div>
        ) : null}
        {stickerOpen ? (
          <StickerDrawer
            onClose={() => setStickerOpen(false)}
            onSendSticker={sendSticker}
            onStatusChange={setStickerStatus}
          />
        ) : null}
        <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
          <Button type="button" variant="ghost" aria-expanded={documentOpen} disabled={replyBusy} onClick={() => setDocumentOpen((value) => !value)}>
            引用本机文档
          </Button>
          {studyDocuments.map((resource) => (
            <div key={resource.id} className="flex items-center gap-2 rounded-[var(--radius-md)] border border-[var(--border)] px-2 py-1">
              <span className="max-w-52 truncate" title={resource.title}>{resource.title}</span>
              <button type="button" aria-label={`移除引用 ${resource.title}`} onClick={() => setStudyDocuments((current) => current.filter(({ id }) => id !== resource.id))}>
                <XIcon size={14} />
              </button>
            </div>
          ))}
        </div>
        {documentOpen ? (
          <div className="mb-2 space-y-2 rounded-[var(--radius-md)] border border-[var(--border)] p-2">
            <p className="text-xs text-[var(--foreground-muted)]">使用原文件，资料库只保存引用和索引。发送后，所选聊天模型会收到引用的正文片段。</p>
            <div className="flex gap-2">
              <input aria-label="聊天文档路径" placeholder="粘贴原文件的完整 Windows 路径" value={documentPath}
                className="min-w-0 flex-1 rounded border border-[var(--border)] px-2 text-sm"
                onChange={(event) => setDocumentPath(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); referenceDocument(); } }} />
              <Button type="button" variant="secondary" onClick={referenceDocument}
                disabled={!documentPath.trim() || !sessionId || studyDocuments.length >= 4 || documentReference.isPending}>
                {documentReference.isPending ? "正在引用…" : "加入并引用"}
              </Button>
            </div>
          </div>
        ) : null}
        {documentNotice ? <p className="mb-2 text-xs" role="status">{documentNotice}</p> : null}
        {attachments.length ? (
          <div className="mb-2 flex gap-2 overflow-x-auto" aria-label="待发送图片">
            {attachments.map((item) => (
              <figure key={item.id} className="relative m-0 size-20 shrink-0 overflow-hidden rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)]">
                <img src={item.dataUrl} alt={item.name} className="h-full w-full object-cover" />
                <button type="button" aria-label={`移除 ${item.name}`} onClick={() => setAttachments((current) => current.filter((entry) => entry.id !== item.id))} className="absolute right-1 top-1 grid size-7 place-items-center rounded-full bg-[#171a21]/80 text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">
                  <XIcon size={14} />
                </button>
              </figure>
            ))}
          </div>
        ) : null}
        <div className="flex items-end gap-2 rounded-[var(--radius-lg)] border border-[var(--border-strong)] bg-[var(--surface-raised)] p-2 shadow-[0_12px_32px_rgba(56,48,39,0.10)] focus-within:ring-2 focus-within:ring-[var(--focus)]">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            className="sr-only"
            onChange={attachFiles}
          />
          <Button
            type="button"
            size="icon"
            variant="ghost"
            aria-label="添加附件"
            title="添加图片"
            disabled={replyBusy}
            onClick={() => fileRef.current?.click()}
          >
            <ImageIcon size={20} />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="relative"
            aria-label="Honey 表情包"
            title="Honey 表情包"
            aria-expanded={stickerOpen}
            onClick={() => setStickerOpen((current) => !current)}
          >
            <SmileyIcon size={20} />
            {stickerStatus?.warning ? (
              <span
                className="absolute right-0.5 top-0.5 size-2 rounded-full bg-[var(--danger)]"
                aria-label="表情包接近容量上限"
              />
            ) : null}
          </Button>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            rows={1}
            placeholder={`和${name}说句话`}
            aria-label="消息"
            disabled={replyBusy}
            className="max-h-40 min-h-11 flex-1 resize-none overflow-y-auto bg-transparent px-3 py-2.5 text-[15px] leading-6 outline-none placeholder:text-[var(--foreground-faint)] [field-sizing:content]"
          />
          <Button type="submit" size="icon" aria-label="发送消息" title="发送消息" disabled={replyBusy || chatModelBusy || documentReference.isPending || (!draft.trim() && !attachments.length && !studyDocuments.length) || !sessionId || !sessionKey}>
            <ArrowUpIcon size={20} weight="bold" />
          </Button>
          {replyBusy ? (
            <Button type="button" size="icon" variant="secondary" aria-label="停止回复" title="停止回复" onClick={stopOrFinishReply}>
              <StopIcon size={18} weight="fill" />
            </Button>
          ) : (
            <Button type="button" size="icon" variant="secondary" aria-label="让 AI 回复" title="让 AI 回复" disabled={chatModelBusy || !queuedMessages.length || !sessionId || !sessionKey} onClick={() => void generateReply()}>
              <PaperPlaneTiltIcon size={20} weight="fill" />
            </Button>
          )}
        </div>
        {attachmentError ? <p className="mt-2 text-center text-xs text-[var(--danger)]" role="alert">{attachmentError}</p> : null}
        {timelineError ? <p className="mt-2 text-center text-xs text-[var(--danger)]" role="alert">{timelineError}</p> : null}
        {newConversation.isError ? <p className="mt-2 text-center text-xs text-[var(--danger)]" role="alert">刚才没有新建成功，请再试一次</p> : null}
      </form>
    </section>
  );
}


function StudyAssistantContent({ content, messageId }: { content: string; messageId: string }) {
  const { text, draft } = splitStudyPlanDraft(content);
  return <>
    {text && <HoneyMessage content={text} role="assistant" messageId={messageId} />}
    {draft && <StudyPlanDraft key={draft.markdown} draft={draft} />}
  </>;
}
