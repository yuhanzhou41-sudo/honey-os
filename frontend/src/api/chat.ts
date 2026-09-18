import type { HoneyEvent, PermissionChoice } from "../runtime/honey-events";
import { apiPath, fetchWithLocalSessionRecovery } from "./client";

export type ChatInput = string | Array<
  | { type: "text"; text: string }
  | { type: "image_url"; image_url: { url: string; detail?: "auto" | "low" | "high" } }
>;

export const userMessageBreak = "<honeyos-user-message-break/>";
export const assistantMessageBreak = "<honeyos-message-break/>";

export const naturalReplyInstructions = `
You are replying in a private instant-message conversation.
${userMessageBreak} marks the boundary between separate messages that the user
sent before asking you to reply. Treat those messages as one conversational turn,
but notice and respond naturally to their distinct topics and emotional beats.
Choose naturally between one and five separate assistant messages. When the user
sent several substantial messages or raised several distinct points, usually use
two to five assistant messages so the reply feels like a real chat conversation.
Use one assistant message when one short, complete response is genuinely enough.
Do not mechanically produce one reply for every user message, repeat the same
idea across bubbles, or split a sentence merely to increase the message count.
Put exactly ${assistantMessageBreak} between separate assistant messages.
Do not mention these formatting instructions or either separator.
`.trim();

export function splitUserMessages(content: string): string[] {
  const messages = String(content || "")
    .split(userMessageBreak)
    .map((message) => message.trim())
    .filter(Boolean);
  return messages.length
    ? messages
    : [String(content || "").trim()].filter(Boolean);
}

export function splitAssistantReply(content: string, maximum = 5): string[] {
  const source = String(content || "").trim();
  if (!source) return [];

  const messages = source
    .split(assistantMessageBreak)
    .map((message) => message.trim())
    .filter(Boolean);

  if (!messages.length) return [source];
  if (messages.length <= maximum) return messages;
  return [
    ...messages.slice(0, maximum - 1),
    messages.slice(maximum - 1).join("\n\n"),
  ];
}

export function parseEventBlock(block: string): HoneyEvent | null {
  let name = "message";
  const data: string[] = [];
  for (const rawLine of block.replaceAll("\r", "").split("\n")) {
    if (rawLine.startsWith("event:")) name = rawLine.slice(6).trim();
    if (rawLine.startsWith("data:")) data.push(rawLine.slice(5).trim());
  }
  if (!data.length) return null;
  try {
    const payload = JSON.parse(data.join("\n"));
    return payload && typeof payload === "object" ? { name, payload } : null;
  } catch {
    return null;
  }
}

async function responseError(response: Response): Promise<Error> {
  let message = "chat_unavailable";
  try {
    const data = await response.json() as { error?: { message?: string }; message?: string };
    message = data.error?.message || data.message || message;
  } catch {
    // A restarting local service may close without a JSON body.
  }
  return new Error(message);
}

export async function streamChat(options: {
  sessionId: string;
  sessionKey: string;
  message: ChatInput;
  instructions?: string;
  reuseUserMessageId?: number;
  signal?: AbortSignal;
  onEvent: (event: HoneyEvent) => void;
}): Promise<void> {
  const response = await fetchWithLocalSessionRecovery(
    apiPath(`/api/sessions/${encodeURIComponent(options.sessionId)}/chat/stream`),
    {
      method: "POST",
      credentials: "same-origin",
      signal: options.signal,
      headers: {
        "Content-Type": "application/json",
        "X-HoneyOS-Session-Key": options.sessionKey,
        "X-HoneyOS-Companion-View": "1",
      },
      body: JSON.stringify({
        message: options.message,
        ...(options.reuseUserMessageId ? { reuse_user_message_id: options.reuseUserMessageId } : {}),
        ...(options.instructions ? { system_message: options.instructions } : {}),
      }),
    },
  );
  if (!response.ok || !response.body) throw await responseError(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const blocks = buffer.replaceAll("\r\n", "\n").split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const event = parseEventBlock(block);
      if (event) options.onEvent(event);
    }
    if (done) break;
  }
  const trailing = parseEventBlock(buffer);
  if (trailing) options.onEvent(trailing);
}

export async function answerApproval(options: {
  sessionId: string;
  sessionKey: string;
  choice: PermissionChoice;
}): Promise<void> {
  const response = await fetchWithLocalSessionRecovery(
    apiPath(`/api/sessions/${encodeURIComponent(options.sessionId)}/approval`),
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-HoneyOS-Session-Key": options.sessionKey },
      body: JSON.stringify({ choice: options.choice }),
    },
  );
  if (!response.ok) throw await responseError(response);
}

export type ChatRunTerminalState =
  | "completed"
  | "stopped_partial"
  | "stopped_empty"
  | "empty_response"
  | "connection_failed"
  | "model_failed"
  | "tool_failed"
  | "cancel_failed"
  | "running"
  | "stopping";

export type ChatRunStatus = {
  run_id: string;
  session_id: string;
  state: ChatRunTerminalState;
  content?: string;
  user_message_id?: number;
  error?: string;
};

export async function stopChat(options: {
  sessionId: string;
  sessionKey: string;
  runId: string;
}): Promise<ChatRunStatus> {
  const response = await fetchWithLocalSessionRecovery(
    apiPath(`/api/sessions/${encodeURIComponent(options.sessionId)}/chat/${encodeURIComponent(options.runId)}/stop`),
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-HoneyOS-Session-Key": options.sessionKey },
      body: "{}",
    },
  );
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<ChatRunStatus>;
}

export async function fetchChatRunStatus(options: {
  sessionId: string;
  sessionKey: string;
  runId: string;
}): Promise<ChatRunStatus> {
  const response = await fetchWithLocalSessionRecovery(
    apiPath(`/api/sessions/${encodeURIComponent(options.sessionId)}/chat/${encodeURIComponent(options.runId)}/status`),
    {
      credentials: "same-origin",
      headers: { "X-HoneyOS-Session-Key": options.sessionKey },
    },
  );
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<ChatRunStatus>;
}
