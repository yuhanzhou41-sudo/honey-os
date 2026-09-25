import { ArrowClockwiseIcon, ArrowDownIcon, ArrowUpIcon, ClockCounterClockwiseIcon, ImageIcon, PaperPlaneTiltIcon, PlusIcon, StopIcon, TrashIcon, XIcon } from "@phosphor-icons/react";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  answerApproval,
  fetchChatRunStatus,
  naturalReplyInstructions,
  splitAssistantReply,
  splitUserMessages,
  stopChat,
  streamChat,
  userMessageBreak,
  watchSessionMessages,
  type ChatInput,
  type ChatRunStatus,
} from "../../api/chat";
import { fetchModelOptions, type ModelOptions } from "../../api/models";
import { CHAT_DOCUMENT_ACCEPT, chatStudyDocumentContext, uploadChatStudyDocument, type ChatStudyDocument } from "../../api/chat-study-library";
import { deleteCompanionConversation, fetchCompanionMessages, rollbackCompanionTimeline, startNewCompanionConversation, switchCompanionConversation, type ChatMessage, type HistoryItem } from "../../api/companion";
import { HoneyAvatar } from "../../components/honey/HoneyAvatar";
import { HoneyMessage } from "../../components/honey/HoneyMessage";
import { ErrorState, LoadingState } from "../../components/honey/PageState";
import { Button } from "../../components/ui/Button";
import type { PermissionChoice } from "../../runtime/honey-events";
import { useHoneyStore } from "../../runtime/honey-store";
import { HoneyRun } from "./HoneyRun";

type ChatAttachment = { id: string; name: string; dataUrl: string };
type QueuedMessage = { id: string; display: string; input: ChatInput };
type RevealingReply = { content: string; visibleCount: number; total: number };

const draftKey = (sessionId: string) => `honeyos-chat-draft:${sessionId}`;
const queueKey = (sessionId: string) => `honeyos-chat-pending:${sessionId}`;

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

function AssistantTurn({ name, children, live = false }: { name: string; children: ReactNode; live?: boolean }) {
  return (
    <article className="flex w-full items-start gap-3 text-[15px] leading-7" aria-live={live ? "polite" : undefined}>
      <HoneyAvatar name={name} className="mt-1 size-8 rounded-full text-xs" />
      <div className="min-w-0 flex-1 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] px-4 py-4 shadow-[0_8px_24px_rgba(56,48,39,0.05)] sm:px-5">
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
  const {
    loading, error, messages, name, status, sessionId, sessionKey, run, sending, history,
    queueUserMessage, beginReply, applyRunEvent, finishTurn, finishStoppedTurn, finishStoppedEmpty,
    replaceTimelineMessages, mergeTimelineMessages, failTurn, startConversation,
    switchConversation, removeHistory, rollbackLocalMessages,
  } = useHoneyStore();
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [queuedMessages, setQueuedMessages] = useState<QueuedMessage[]>([]);
  const [submittedMessages, setSubmittedMessages] = useState<QueuedMessage[]>([]);
  const [revealingReply, setRevealingReply] = useState<RevealingReply | null>(null);
  const [attachmentError, setAttachmentError] = useState("");
  const [approvalPending, setApprovalPending] = useState(false);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [stoppedReply, setStoppedReply] = useState(false);
  const [stoppedUserMessageId, setStoppedUserMessageId] = useState<number | null>(null);
  const [recoverRunId, setRecoverRunId] = useState<string | null>(null);
  const [retryUserMessageId, setRetryUserMessageId] = useState<number | null>(null);
  const [timelineError, setTimelineError] = useState("");
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
      setRevealingReply(null);
      startConversation(data.session_id, data.session_key);
    },
  });
  const switchConversationMutation = useMutation({
    mutationFn: switchCompanionConversation,
    onSuccess: (data) => {
      setQueuedMessages([]);
      setSubmittedMessages([]);
      setRevealingReply(null);
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

  useEffect(() => {
    if (!revealingReply) return;
    const finished = revealingReply.visibleCount >= revealingReply.total;
    const timer = window.setTimeout(() => {
      if (finished) {
        setRevealingReply(null);
      } else {
        setRevealingReply((current) => current ? {
          ...current,
          visibleCount: Math.min(current.total, current.visibleCount + 1),
        } : null);
      }
    }, finished ? 300 : 700);
    return () => window.clearTimeout(timer);
  }, [revealingReply]);

  function finishWithStatus(status: ChatRunStatus): boolean {
    if (status.content) {
      applyRunEvent({
        name: "assistant.completed",
        payload: { content: status.content, terminal_state: status.state, recovered: true },
      });
    }
    if (status.state === "completed") {
      finishTurn();
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
        if (finishWithStatus(status)) return;
      } catch {
        break;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 300));
    }
    failTurn("连接中断，尚未取回原回复；重新连接不会重复发送你的消息");
  }

  async function generateReply() {
    if (!queuedMessages.length || sending || !sessionId || !sessionKey) return;
    const submitted = [...queuedMessages];
    followRef.current = true;
    setStoppedReply(false);
    setStoppedUserMessageId(null);
    setRecoverRunId(null);
    setRetryUserMessageId(null);
    beginReply();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let terminalStatus: ChatRunStatus | null = null;
      await streamChat({
        sessionId,
        sessionKey,
        message: combineQueuedInputs(queuedMessages),
        instructions: naturalReplyInstructions,
        signal: controller.signal,
        onEvent: (event) => {
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
      if (terminalStatus && finishWithStatus(terminalStatus)) return;
      const completedRun = useHoneyStore.getState().run;
      const reply = completedRun.parts
        .filter((part) => part.kind === "text")
        .map((part) => part.content)
        .filter(Boolean)
        .join("\n\n") || completedRun.content;
      const replyCount = splitAssistantReply(reply).length;
      if (replyCount > 1) {
        setRevealingReply({ content: reply, visibleCount: 1, total: replyCount });
      }
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
    if (sending) return;
    const text = draft.trim();
    if (!text && !attachments.length) return;
    const message = [text, ...attachments.map((item) => `![${item.name}](${item.dataUrl})`)].filter(Boolean).join("\n\n");
    const input: ChatInput = attachments.length ? [
      ...(text ? [{ type: "text" as const, text }] : []),
      ...attachments.map((item) => ({ type: "image_url" as const, image_url: { url: item.dataUrl, detail: "auto" as const } })),
    ] : text;
    setDraft("");
    if (sessionId) localStorage.removeItem(draftKey(sessionId));
    setAttachments([]);
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
        if (status.state === "cancel_failed") finishWithStatus(status);
      } catch {
        failTurn("停止请求失败；不会自动重新发送你的消息");
      }
      return;
    }
    setRevealingReply((current) => current ? {
      ...current,
      visibleCount: current.total,
    } : null);
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
    beginReply();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let terminalStatus: ChatRunStatus | null = null;
      await streamChat({
        sessionId, sessionKey, message: combineQueuedInputs(pending),
        instructions: naturalReplyInstructions,
        reuseUserMessageId,
        signal: controller.signal,
        onEvent: (event) => {
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
      if (terminalStatus && finishWithStatus(terminalStatus)) return;
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

  async function attachImages(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []).slice(0, Math.max(0, 4 - attachments.length));
    event.target.value = "";
    if (!files.length) return;
    setAttachmentError("");
    try {
      const next = await Promise.all(files.map(async (file) => ({
        id: `${file.name}-${file.lastModified}-${file.size}`,
        name: file.name,
        dataUrl: await readChatImage(file),
      })));
      setAttachments((current) => [...current, ...next].slice(0, 4));
    } catch {
      setAttachmentError("图片没有读出来，请使用小于 15MB 的常见图片格式");
    }
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

  async function respondToApproval(choice: PermissionChoice) {
    if (!sessionId || !sessionKey || approvalPending) return;
    setApprovalPending(true);
    try {
      await answerApproval({ sessionId, sessionKey, choice });
      applyRunEvent({ name: "approval.responded", payload: { choice } });
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
    let parts = message.role === "assistant"
      ? splitAssistantReply(message.content)
      : splitUserMessages(message.content);
    const isRevealingLatest = message.role === "assistant"
      && messageIndex === recentMessages.length - 1
      && revealingReply?.content === message.content;
    if (isRevealingLatest) parts = parts.slice(0, revealingReply.visibleCount);
    return parts.map((content, partIndex) => ({
      ...message,
      content,
      displayKey: `${message.role}-${messageIndex}-${partIndex}`,
      partIndex,
      sourceIndex: recentStart + messageIndex,
    }));
  });
  const activityRun = {
    ...run,
    content: "",
    parts: run.parts.filter((part) => part.kind !== "text"),
  };
  const replyBusy = sending || Boolean(revealingReply);
  return (
    <section className="relative flex h-full min-h-0 w-full flex-col bg-[var(--background)] px-3 sm:px-7">
      <header className="mx-auto flex min-h-[4.75rem] w-full max-w-[56rem] shrink-0 items-center gap-3 border-b border-[var(--border)] px-1">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold tracking-[-0.02em]">{name}</h1>
          <p className="truncate text-xs text-[var(--foreground-muted)]">{replyBusy ? "正在陪你聊" : status}</p>
        </div>
        <Button className="ml-auto" type="button" size="icon" variant="ghost" aria-label="历史聊天" title="历史聊天" onClick={() => setHistoryOpen((open) => !open)}>
          <ClockCounterClockwiseIcon size={20} />
        </Button>
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
      </header>

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
              <AssistantTurn key={message.displayKey} name={name}>
                <HoneyMessage
                  content={message.content}
                  role={message.role}
                  messageId={message.displayKey}
                />
                {message.timeline_editable && message.id ? (
                  <div className="mt-2 flex justify-end">
                    <Button type="button" variant="ghost" onClick={() => void rollbackMessage(message, "regenerate")}>
                      <ArrowClockwiseIcon size={15} />重新生成
                    </Button>
                  </div>
                ) : null}
              </AssistantTurn>
            ) : (
              <article key={message.displayKey} className="ml-auto flex max-w-[92%] items-start gap-2 text-[15px] leading-7 sm:max-w-[78%]">
                <div className="min-w-0 rounded-[var(--radius-lg)] bg-[var(--surface-subtle)] px-4 py-3">
                  <HoneyMessage
                    content={message.content}
                    plain={!message.content.includes("data:image/")}
                    role={message.role}
                    messageId={message.displayKey}
                  />
                  {message.timeline_editable && message.id ? (
                    <div className="mt-1 flex justify-end">
                      <Button type="button" variant="ghost" aria-label="删除并回滚后续聊天" onClick={() => void rollbackMessage(message, "delete", message.partIndex)}>
                        <TrashIcon size={14} />删除
                      </Button>
                    </div>
                  ) : !message.id ? (
                    <div className="mt-1 flex justify-end gap-1">
                      <Button type="button" variant="ghost" onClick={() => rollbackLocalMessage(message.sourceIndex, message.partIndex, true)}>编辑</Button>
                      <Button type="button" variant="ghost" onClick={() => rollbackLocalMessage(message.sourceIndex, message.partIndex, false)}>删除</Button>
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
        {run.phase !== "idle" ? (
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

      <form className="mx-auto w-full max-w-[56rem] shrink-0 pb-[calc(14px+env(safe-area-inset-bottom))] pt-2" onSubmit={send}>
        {stoppedReply && queuedMessages.length && !replyBusy ? (
          <div className="mb-2 flex justify-center">
            <Button type="button" variant="secondary" onClick={regenerateStoppedReply}>
              <ArrowClockwiseIcon size={16} />
              重新生成
            </Button>
          </div>
        ) : null}
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
          <input ref={fileRef} type="file" accept="image/*" multiple className="sr-only" onChange={attachImages} />
          <Button type="button" size="icon" variant="ghost" aria-label="添加图片" disabled={replyBusy || attachments.length >= 4} onClick={() => fileRef.current?.click()}>
            <ImageIcon size={20} />
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
          <Button type="submit" size="icon" aria-label="发送消息" title="发送消息" disabled={replyBusy || (!draft.trim() && !attachments.length) || !sessionId || !sessionKey}>
            <ArrowUpIcon size={20} weight="bold" />
          </Button>
          {replyBusy ? (
            <Button type="button" size="icon" variant="secondary" aria-label="停止回复" title="停止回复" onClick={stopOrFinishReply}>
              <StopIcon size={18} weight="fill" />
            </Button>
          ) : (
            <Button type="button" size="icon" variant="secondary" aria-label="让 AI 回复" title="让 AI 回复" disabled={!queuedMessages.length || !sessionId || !sessionKey} onClick={() => void generateReply()}>
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
