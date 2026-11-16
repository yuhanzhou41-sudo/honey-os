import { useState } from "react";
import { Link } from "react-router-dom";
import { confirmChatStudyPlan, previewChatStudyPlan, type PlanningPreview } from "../../api/study-planning";
import { Button } from "../../components/ui/Button";

export function splitStudyPlanDraft(content: string) {
  const fence = String.fromCharCode(96).repeat(3);
  const pattern = new RegExp(fence + "(study-plan(?:-update)?) *\\r?\\n([\\s\\S]*?)\\r?\\n" + fence);
  const match = pattern.exec(content);
  if (!match) return { text: content };
  return {
    text: (content.slice(0, match.index) + content.slice(match.index + match[0].length)).trim(),
    draft: { markdown: match[2], revision: match[1] === "study-plan-update" },
  };
}

export default function StudyPlanDraft({ draft }: {
  draft: { markdown: string; revision: boolean };
}) {
  const [preview, setPreview] = useState<PlanningPreview>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  async function act() {
    setBusy(true);
    setError("");
    try {
      if (preview) {
        await confirmChatStudyPlan(draft, preview);
        setDone(true);
      } else {
        setPreview(await previewChatStudyPlan(draft));
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "计划处理失败，请重试。");
      if (preview && draft.revision) setPreview(undefined);
    } finally {
      setBusy(false);
    }
  }

  return <section aria-label="学习计划草案" className="my-2 space-y-2 rounded border border-[var(--border)] bg-[var(--surface-raised)] p-3">
    <strong>{draft.revision ? "学习计划调整草案" : "学习计划草案"}</strong>
    {preview && <div className="space-y-1">
      <p>{preview.plan.title} · {preview.plan.start_date} 至 {preview.plan.end_date}</p>
      <ol className="max-h-64 list-decimal overflow-auto pl-5">
        {preview.plan.tasks.map(task => <li key={task.id}>
          {task.scheduled_date} · {task.title} · {task.planned_minutes} 分钟{task.status === "completed" ? " · 已完成" : ""}{task.description ? " · " + task.description : ""}
        </li>)}
      </ol>
      {draft.revision && <p className="text-sm">调整后，原任务上已设置的提醒会同步更新。</p>}
    </div>}
    {error && <p role="alert">{error}</p>}
    {done ? <p role="status">计划已保存。 <Link className="underline" to="/study">打开放在学习页面的计划</Link></p> :
      <Button type="button" variant="secondary" disabled={busy} onClick={() => void act()}>
        {busy ? "正在处理…" : preview ? (draft.revision ? "确认调整计划" : "确认保存到学习") : "预览学习计划"}
      </Button>}
  </section>;
}
