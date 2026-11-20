import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { listStudyResources, type StudyPlan } from "../../api/study";
import {
  buildPlanningRequest, getStudyPlanningCapabilities,
} from "../../api/study-planning";

export default function PlanningRequestBuilder({ plan }: { plan?: StudyPlan }) {
  const [open, setOpen] = useState(false);
  const [revision, setRevision] = useState(false);
  const [objective, setObjective] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [constraints, setConstraints] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [markdown, setMarkdown] = useState("");
  const [copyNotice, setCopyNotice] = useState("");
  const capabilities = useQuery({
    queryKey: ["study-planning-capabilities"], queryFn: getStudyPlanningCapabilities,
    enabled: open, retry: false,
  });
  const resources = useQuery({
    queryKey: ["study-planning-resources"], queryFn: () => listStudyResources(),
    enabled: open, retry: false,
  });
  const build = useMutation({
    mutationFn: () => buildPlanningRequest({
      objective, start_date: start, end_date: end, constraints,
      resource_ids: selected, ...(revision && plan ? { plan_id: plan.id } : {}),
    }),
    onSuccess: value => { setMarkdown(value); setCopyNotice(""); },
  });

  async function copyRequest() {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopyNotice("已复制，可连同上方新模板或当前计划一起交给外部 AI。");
    } catch {
      setCopyNotice("复制失败，请手动选择下方预览文字复制。");
    }
  }

  return <details className="mt-3 rounded border border-[var(--border)] p-3"
    onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-sm">交给其他 AI 制定计划</summary>
    {capabilities.data && <p className="my-2 text-sm">
      当前格式 V{capabilities.data.supported_schema_version}。格式规则已包含在上方新计划模板和当前计划文件中。这里仅整理目标、所选资料与容量信息，不是可导入计划。
    </p>}
    {capabilities.isError && <p role="alert">当前版本能力暂时无法读取。</p>}
    <form onChangeCapture={() => { setMarkdown(""); setCopyNotice(""); }} onSubmit={event => {
      event.preventDefault(); setMarkdown(""); build.mutate();
    }}>
      <fieldset disabled={build.isPending} className="my-3 space-y-3 text-sm">
        {plan && <label className="flex gap-2">
          <input type="checkbox" checked={revision} onChange={event => {
            setRevision(event.target.checked);
            if (event.target.checked) { setStart(plan.start_date); setEnd(plan.end_date); }
          }} />
          调整当前计划「{plan.title}」
        </label>}
        <label className="block">学习目标与考试范围
          <textarea required maxLength={2000} value={objective} onChange={event => setObjective(event.target.value)}
            className="mt-1 w-full rounded border border-[var(--border)] p-2" />
        </label>
        <div className="flex flex-wrap gap-3">
          <label>计划开始日期 <input required type="date" value={start} onChange={event => setStart(event.target.value)} /></label>
          <label>计划结束日期 <input required type="date" min={start} value={end} onChange={event => setEnd(event.target.value)} /></label>
        </div>
        <label className="block">可用时段、固定安排与其他要求
          <textarea maxLength={6000} value={constraints} onChange={event => setConstraints(event.target.value)}
            className="mt-1 w-full rounded border border-[var(--border)] p-2" />
        </label>
        <p className="text-xs text-[var(--foreground-muted)]">最多选择8份资料，请求将包含标题和每份最多2000字的正文片段。可先检查下方预览再下载。</p>
        {resources.isError && <p role="alert">资料列表暂时无法读取。</p>}
        {resources.data?.resources.map(resource => <label key={resource.id} className="flex gap-2">
          <input type="checkbox" checked={selected.includes(resource.id)} disabled={!selected.includes(resource.id) && selected.length >= 8} onChange={event => {
            setSelected(current => event.target.checked
              ? [...current, resource.id] : current.filter(id => id !== resource.id));
          }} />
          {resource.title}
        </label>)}
        <button type="submit" disabled={!capabilities.data} className="text-[var(--accent)]">
          {build.isPending ? "正在生成…" : "预览规划请求"}
        </button>
      </fieldset>
    </form>
    {build.error && <p role="alert">{build.error.message}</p>}
    {markdown && <div className="space-y-2">
      <textarea aria-label="规划请求预览" readOnly value={markdown} rows={12}
        className="w-full rounded border border-[var(--border)] p-2 text-xs" />
      <button type="button" onClick={copyRequest} className="text-sm text-[var(--accent)]">复制请求给外部 AI</button>
      {copyNotice && <p role="status" className="text-xs">{copyNotice}</p>}
      <p className="text-xs text-[var(--foreground-muted)]">新建时让 AI 单独输出 study_plan.md 和 planning_notes.md，只导入 study_plan.md；调整当前计划时保留 ID，将结果交回 Honey 聊天进行调整预览，不重复导入。</p>
    </div>}
  </details>;
}
