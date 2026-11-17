import { useState } from "react";
import { saveReplyFeedback, type ReplyFeedback as Feedback } from "../../api/companion";

export function ReplyFeedback({ sessionId, sessionKey, messageId, initial }: {
  sessionId: string;
  sessionKey: string;
  messageId: number;
  initial?: Feedback | null;
}) {
  const [saved, setSaved] = useState(initial ?? null);
  const [rating, setRating] = useState<Feedback["rating"] | null>(initial?.rating ?? null);
  const [note, setNote] = useState(initial?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  async function save(feedback: Feedback | null) {
    setBusy(true);
    setStatus("");
    try {
      const result = await saveReplyFeedback(sessionId, sessionKey, messageId, feedback);
      setSaved(result.feedback);
      setRating(result.feedback?.rating ?? null);
      setNote(result.feedback?.note ?? "");
      setStatus(feedback ? "已保存" : "已撤回");
    } catch {
      setStatus("保存失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="mt-2 text-xs text-[var(--foreground-muted)]" onClick={(event) => event.stopPropagation()}>
      <summary className="w-fit cursor-pointer">{saved ? "已反馈" : "反馈这条回复"}</summary>
      <fieldset disabled={busy} className="mt-2 flex flex-col gap-2">
        <div className="flex gap-3">
          <label><input type="radio" name={`reply-${messageId}`} checked={rating === "like"} onChange={() => setRating("like")} /> 点赞</label>
          <label><input type="radio" name={`reply-${messageId}`} checked={rating === "dislike"} onChange={() => setRating("dislike")} /> 不喜欢</label>
        </div>
        <textarea aria-label="反馈备注" className="rounded border p-2" placeholder="备注（可选）" maxLength={500} value={note} onChange={(event) => setNote(event.target.value)} />
        <div className="flex gap-3">
          <button type="button" disabled={!rating} onClick={() => rating && void save({ rating, note })}>保存反馈</button>
          {saved && <button type="button" onClick={() => void save(null)}>撤回</button>}
          <span role="status">{status}</span>
        </div>
      </fieldset>
    </details>
  );
}
