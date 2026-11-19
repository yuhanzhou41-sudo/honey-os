export const legacyAssistantMessageBreak = "<honeyos-message-break/>";

const STRUCTURED_TURN_PATTERNS = [
  /详细/u, /分析/u, /总结/u, /整理/u, /对比/u, /比较/u, /步骤/u, /表格/u,
  /代码/u, /调试/u, /报错/u, /错误/u, /\bbug\b/iu, /\bgit\b/iu, /\bcommit\b/iu,
  /\bpytest\b/iu, /\bnpm\b/iu, /\bapi\b/iu, /\bsql\b/iu, /数据库/u, /接口/u,
  /脚本/u, /函数/u, /编译/u, /构建/u, /测试/u, /算法/u, /论文/u, /实验/u,
  /统计/u, /考试/u, /复习/u, /名词解释/u, /文档/u, /报告/u, /```/u,
  /\.(?:pdf|docx?|pptx?|xlsx?|csv|jsonl?|py|ts|tsx|js|jsx)\b/iu,
  /explain in detail/iu, /\bcompare\b/iu, /step[- ]by[- ]step/iu,
  /analy[sz]e/iu, /\bsummar(?:y|ize)\b/iu, /\bdebug\b/iu, /\bcode\b/iu,
  /\breport\b/iu, /\btable\b/iu,
];

const STRUCTURED_REPLY = /^[ \t]*(?:#{1,6}[ \t]|[-+*>][ \t]|[0-9]+[.)][ \t]|[|]|~{3,}|-{3,}$|={3,}$)|^(?: {4}|\t)\S|\x60{3,}|\$|\\(?:\[|\()|https?:\/\/|www\.|\]\(/imu;

const STRONG_BOUNDARIES = new Set(["。", "！", "？", "!", "?"]);
const WEAK_BOUNDARIES = new Set(["，", ",", "；", ";"]);
const OPEN_TO_CLOSE: Record<string, string> = {
  "(": ")", "（": "）", "[": "]", "【": "】", "{": "}", "“": "”", "‘": "’",
};

const GREETING_OR_REACTION = /^(?:早上好|早安|午安|下午好|晚上好|晚安|你好|嗨|哈喽|hello|hey|hi|嗯+|唔+|诶+|欸+|哎+|哇+|哈哈+|好呀|好哦|好诶)/iu;

const DEPENDENCY_PAIRS: Array<[RegExp, RegExp]> = [
  [/^因为/u, /所以/u],
  [/^如果/u, /(?:那么|那就|就)/u],
  [/^虽然/u, /(?:但是|但|不过|却)/u],
  [/^尽管/u, /(?:但是|但|不过|却)/u],
  [/^除非/u, /(?:否则|不然|才)/u],
  [/^只要/u, /(?:就|便)/u],
  [/^无论/u, /(?:都|也)/u],
  [/^不管/u, /(?:都|也)/u],
  [/^不仅/u, /(?:而且|还|也)/u],
  [/^一方面/u, /另一方面/u],
];

const TRAILING_DEPENDENCY = /(?:因为|如果|虽然|尽管|除非|只要|为了|由于|例如|比如|包括|也就是说|换句话说|不仅|一方面|然后|接着|还有|以及|或者|并且|而且|所以|但是|不过|至于|关于|的|地|得|把|被|让|给|向|从|将|会|正在|需要|想要|觉得|认为|就是|是)$/u;

export type BubbleSegmentation = {
  sealed: string[];
  partial: string;
};

export function isStructuredChatTurn(userText: string): boolean {
  const text = String(userText || "").trim();
  if (!text) return false;
  return STRUCTURED_TURN_PATTERNS.some((pattern) => pattern.test(text));
}

function visibleLength(text: string): number {
  return Array.from(text.replace(/\s+/gu, "")).length;
}

function normalizeBoundaryText(raw: string, boundary: string): string {
  let value = raw.trim();
  if (WEAK_BOUNDARIES.has(boundary)) {
    value = value.replace(/[，,；;]\s*$/u, "").trim();
  }
  return value;
}

function weakBoundaryIsComplete(raw: string, boundary: string): boolean {
  const bare = normalizeBoundaryText(raw, boundary);
  if (!bare) return false;
  for (const [open, close] of DEPENDENCY_PAIRS) {
    if (open.test(bare) && !close.test(bare)) return false;
  }
  if (TRAILING_DEPENDENCY.test(bare)) return false;
  if (GREETING_OR_REACTION.test(bare)) return true;
  if (boundary === "；" || boundary === ";") return visibleLength(bare) >= 6;
  return visibleLength(bare) >= 18;
}

function looksLikeUrlTail(text: string): boolean {
  return /https?:\/\/[^\s]*$/iu.test(text);
}

export function segmentCasualAssistantText(
  sourceText: string,
): BubbleSegmentation {
  const source = String(sourceText || "");
  if (!source.trim()) return { sealed: [], partial: "" };

  const sealed: string[] = [];
  const stack: string[] = [];
  let cursor = 0;
  let inFence = false;
  let inInlineCode = false;

  for (let index = 0; index < source.length; index += 1) {
    if (source.startsWith("```", index)) {
      inFence = !inFence;
      index += 2;
      continue;
    }

    const char = source[index];
    if (!inFence && char === "`") {
      inInlineCode = !inInlineCode;
      continue;
    }
    if (inFence || inInlineCode) continue;

    if (OPEN_TO_CLOSE[char]) {
      stack.push(OPEN_TO_CLOSE[char]);
      continue;
    }
    if (stack.length && char === stack[stack.length - 1]) {
      stack.pop();
      continue;
    }
    if (stack.length) continue;

    let boundary = "";
    if (char === "\n" && /^[ \t\r]*\n/u.test(source.slice(index + 1))) {
      boundary = "\n";
    } else if (STRONG_BOUNDARIES.has(char)) {
      if (STRONG_BOUNDARIES.has(source[index + 1])) continue;
      if (looksLikeUrlTail(source.slice(cursor, index + 1))) continue;
      boundary = char;
    } else if (char === "…") {
      const previousIsEllipsis = index > cursor && source[index - 1] === "…";
      const next = source[index + 1] || "";
      if (previousIsEllipsis || !next || /\s/u.test(next)) boundary = char;
    } else if (WEAK_BOUNDARIES.has(char)) {
      boundary = char;
    }

    if (!boundary) continue;

    const raw = source.slice(cursor, index + 1);
    const shouldSeal = STRONG_BOUNDARIES.has(boundary) || boundary === "\n" || boundary === "…"
      ? Boolean(raw.trim())
      : weakBoundaryIsComplete(raw, boundary);
    if (!shouldSeal) continue;

    if (raw.trim()) sealed.push(raw.trim());
    cursor = index + 1;
  }

  const partial = source.slice(cursor).trim();
  return { sealed, partial };
}

function splitLegacyAssistantReply(source: string): string[] {
  return source
    .split(legacyAssistantMessageBreak)
    .map((message) => message.trim())
    .filter(Boolean);
}

export function assistantBubblesForDisplay(
  content: string,
  userText: string,
): string[] {
  const source = String(content || "").trim();
  if (!source) return [];

  if (source.includes(legacyAssistantMessageBreak)) {
    return splitLegacyAssistantReply(source);
  }
  if (isStructuredChatTurn(userText) || STRUCTURED_REPLY.test(source)) return [source];

  const result = segmentCasualAssistantText(source);
  const bubbles = [...result.sealed];
  if (result.partial) bubbles.push(result.partial);
  return bubbles.length ? bubbles : [source];
}
