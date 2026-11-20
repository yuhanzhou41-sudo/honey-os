import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getGardenSummary, getStudyGarden, type GardenPlant } from "../../api/study-growth";

function PlantArt({ plant }: { plant: GardenPlant }) {
  const stage = plant.planted ? 5 : ({ 种子: 0, 发芽: 1, 幼苗: 2, 长叶: 3, 花苞: 4 }[plant.plant] ?? 0);
  return <svg viewBox="0 0 160 160" className="mx-auto h-28 w-28" role="img" aria-label={plant.planted ? "已完成计划的纪念花" : plant.plant}>
    <ellipse cx="80" cy="145" rx="46" ry="7" fill="#50684a" opacity=".12" />
    <path d="M51 107H109L102 141Q80 150 58 141Z" fill={plant.planted ? "#b37768" : "#bd946c"} />
    <rect x="47" y="103" width="66" height="10" rx="4" fill={plant.planted ? "#d89d8d" : "#d9b58c"} />
    {stage === 0 ? <ellipse cx="80" cy="96" rx="7" ry="4" fill="#82634b" /> : <>
      <path d={`M80 105 Q76 86 80 ${stage >= 3 ? 48 : 76}`} stroke="#5f8055" strokeWidth="5" fill="none" strokeLinecap="round" />
      <path d="M79 91Q49 93 49 70Q72 69 79 91" fill="#82a971" />
      <path d="M80 82Q109 83 110 59Q85 61 80 82" fill="#638c5d" />
      {stage >= 3 && <path d="M79 66Q58 67 57 47Q75 47 79 66" fill="#a5bd87" />}
      {stage === 4 && <ellipse cx="80" cy="43" rx="10" ry="15" fill="#cf9a9c" />}
      {stage === 5 && <g fill="#dca4ae">
        {[0, 72, 144, 216, 288].map(angle => <ellipse key={angle} cx="80" cy="28" rx="10" ry="16" transform={`rotate(${angle} 80 43)`} />)}
        <circle cx="80" cy="43" r="9" fill="#e3c87c" />
      </g>}
    </>}
  </svg>;
}

export default function StudyGardenPanel({ onSelectPlan, standalone = false }: {
  onSelectPlan?: (id: string) => void; standalone?: boolean;
}) {
  const [open, setOpen] = useState(standalone);
  const [selectedId, setSelectedId] = useState("");
  const [period, setPeriod] = useState("week");
  const [anchor, setAnchor] = useState(() => new Date().toLocaleDateString("en-CA"));
  const garden = useQuery({ queryKey: ["study-garden"], queryFn: getStudyGarden,
    enabled: open, refetchInterval: open ? 30_000 : false, retry: false });
  const plants = garden.data?.plants ?? [];
  const selected = plants.find(plant => plant.plan_id === selectedId) ?? plants[0];
  const report = useQuery({ queryKey: ["study-garden-summary", selected?.plan_id, period, anchor],
    queryFn: () => getGardenSummary(selected!.plan_id, period, anchor),
    enabled: open && Boolean(selected), refetchInterval: open && !selected?.closed ? 30_000 : false, retry: false });
  const content = <div className="space-y-4 p-4">
    <p className="text-sm text-[var(--foreground-muted)]">每份启用成长的计划有一株植物，进度会持续更新。确认完成后，纪念花永久留园；停止的计划保留原生长阶段。这里也能查看独立学习记忆。</p>
    {garden.isLoading && <p role="status">正在查看花园…</p>}
    {garden.isError && <p role="alert">花园暂时无法读取。<button className="ml-2 underline" onClick={() => garden.refetch()}>重试</button></p>}
    {garden.data && plants.length === 0 && <p>花园还没有植物。请先在学习页选择计划并启用成长记录；已确认结束的计划也会保留在这里。</p>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {plants.map(plant => <button key={plant.plan_id} type="button"
        aria-pressed={selected?.plan_id === plant.plan_id}
        onClick={() => setSelectedId(plant.plan_id)}
        className={`rounded-2xl border p-4 text-left transition-colors ${selected?.plan_id === plant.plan_id ? "border-[var(--accent)] bg-[var(--surface-raised)]" : "border-[var(--border)] bg-[var(--surface)]"}`}>
        <PlantArt plant={plant} />
        <span className="block font-medium">{plant.title}</span>
        <span className="mt-1 block text-xs text-[var(--foreground-muted)]">{plant.planted ? "已种入花园 · 纪念花" : plant.closed ? "已停止 · " + plant.plant : "生长中 · " + plant.plant}</span>
        <span className="mt-2 block text-sm">{plant.completed}/{plant.tasks} 项 · {plant.sunlight} 阳光 · {plant.standard_days} 个标准学习日</span>
        <span className="mt-2 block text-xs">点击查看学习记忆与周 / 月 / 年总结</span>
      </button>)}
    </div>
    {selected && <section className="rounded-xl border border-[var(--border)] p-4" aria-label="植物的学习记忆">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">{selected.title} · 学习记忆</h3>
        {!selected.closed && onSelectPlan && <button className="text-sm underline" onClick={() => onSelectPlan(selected.plan_id)}>查看此计划任务</button>}
      </div>
      {selected.summary && <p className="mt-3 text-sm">{selected.summary}</p>}
      <div className="my-4 flex flex-wrap items-center gap-2">
        {([['week', '周总结'], ['month', '月总结'], ['year', '年总结']] as const).map(([value, label]) =>
          <button key={value} aria-pressed={period === value} onClick={() => setPeriod(value)}
            className={`rounded-full border px-3 py-1 text-sm ${period === value ? "border-[var(--accent)] text-[var(--accent)]" : "border-[var(--border)]"}`}>{label}</button>)}
        <label className="text-sm">查看日期 <input aria-label="花园总结日期" type="date" value={anchor} onChange={event => setAnchor(event.target.value)} className="rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1" /></label>
      </div>
      {report.isLoading && <p role="status">正在整理真实学习记录…</p>}
      {report.isError && <p role="alert">学习总结暂时无法读取。<button className="ml-2 underline" onClick={() => report.refetch()}>重试</button></p>}
      {report.data && <>
        <p className="text-xs text-[var(--foreground-muted)]">{report.data.start_date} — {report.data.end_date} · 记录截至 {report.data.as_of}{report.data.archived ? " · 结束时留存" : " · 随学习更新"}</p>
        <p className="mt-2 text-sm leading-7">{report.data.body}</p>
        <details className="mt-3 text-sm"><summary className="cursor-pointer">每日学习记忆与来源（{report.data.days.length} 天）</summary>
          <div className="mt-2 max-h-96 space-y-2 overflow-auto">
            {report.data.days.length === 0 && <p>该时段没有记录，不会生成虚构的学习总结。</p>}
            {report.data.days.map(day => <details key={day.date} className="rounded border border-[var(--border)] p-3">
              <summary className="cursor-pointer">{day.date} · 完成 {day.completed}/{day.tasks} · 专注 {day.focus_minutes} 分钟</summary>
              <p className="mt-2">练习 {day.attempts} 次，答对 {day.correct} 次；闪卡复述 {day.recalls} 次；阳光 {day.reward_points}。</p>
              <p className="mt-1 text-xs text-[var(--foreground-muted)]">来源：{Object.entries(day.sources).map(([kind, ids]) => `${({ tasks: "任务", sessions: "专注", attempts: "答题", recalls: "闪卡" } as Record<string,string>)[kind] ?? kind} ${ids.length} 条`).join(" · ")}</p>
            </details>)}
          </div>
        </details>
        <p className="mt-3 text-xs text-[var(--foreground-muted)]">周从周一开始，月与年按自然日历统计。数字来自真实学习事件；结束后的统计保留在花园，不恢复已清理的周报正文。</p>
      </>}
    </section>}
  </div>;
  return standalone ? <section className="mt-4">{content}</section> : <details className="mt-4 rounded-2xl border border-[var(--border)]" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary className="cursor-pointer px-4 py-3 font-medium">学习花园与记忆 <span className="ml-2 text-xs font-normal text-[var(--foreground-muted)]">植物 · 日记录 · 周 / 月 / 年总结</span></summary>
    {open && content}
  </details>;
}
