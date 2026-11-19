import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { listStudyResources, type StudyPlan } from "../../api/study";
import {
  buildPlanningRequest, getStudyPlanningCapabilities,
  planAuthoringGuideUrl, planTemplateUrl,
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
    onSuccess: setMarkdown,
  });

  function download() {
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "planning_request.md";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <details className="mt-3 rounded border border-[var(--border)] p-3"
    onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer text-sm">交给其他 AI 制定计划</summary>
    {capabilities.data && <p className="my-2 text-sm">
      当前支持 V{capabilities.data.supported_schema_version} ·{" "}
      <a href={planAuthoringGuideUrl()} download className="underline">下载编写指南</a>
      {" · "}<a href={planTemplateUrl(1)} download className="underline">下载 V1 模板</a>
    </p>}
    {capabilities.isError && <p role="alert">当前版本能力暂时无法读取。</p>}
    <form onChangeCapture={() => setMarkdown("")} onSubmit={event => {
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
      <button type="button" onClick={download} className="text-sm text-[var(--accent)]">下载 planning_request.md</button>
      <p className="text-xs text-[var(--foreground-muted)]">让其他 AI 单独输出 study_plan.md 和 planning_notes.md，再把 study_plan.md 导入预览。</p>
    </div>}
  </details>;
}
