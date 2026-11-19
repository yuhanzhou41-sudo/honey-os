import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getStudyCapacity, setStudyDailyCapacity, type StudyCapacityDay, type StudyPlan } from "../../api/study";

export function CapacitySummary({ days }: { days?: StudyCapacityDay[] }) {
  if (!days?.length) return <p className="text-sm">每日学习上限未核实。</p>;
  return <ul aria-label="学习时间容量" className="my-2 space-y-1 text-sm">
    {days.map(day => <li key={day.date} className={day.overloaded ? "text-red-500" : ""}>
      {day.date} · 本计划 {day.candidate_minutes} 分钟 · 其他计划 {day.other_minutes} 分钟
      {" · 合计 "}{day.total_minutes} 分钟
      {day.verified ? " · 上限 " + day.limit_minutes + " 分钟" : " · 上限未核实"}
      {day.overloaded ? " · 超出上限" : ""}
    </li>)}
  </ul>;
}

export default function StudyCapacityPanel({ plan, date }: { plan: StudyPlan; date: string }) {
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ["study-capacity", plan.id, plan.updated_at],
    queryFn: () => getStudyCapacity(plan.id),
    retry: false,
  });
  const day = query.data?.capacity.find(item => item.date === date);
  const [minutes, setMinutes] = useState("");
  useEffect(() => {
    setMinutes(day?.limit_minutes == null ? "" : String(day.limit_minutes));
  }, [date, day?.limit_minutes]);
  const save = useMutation({
    mutationFn: () => {
      const value = minutes.trim() ? Number(minutes) : null;
      if (value !== null && (!Number.isInteger(value) || value < 0 || value > 1440)) {
        throw new Error("请输入0至1440的整数分钟。");
      }
      return setStudyDailyCapacity(date, value);
    },
    onSuccess: () => client.invalidateQueries({ queryKey: ["study-capacity"] }),
  });
  return <details className="my-3 rounded border border-[var(--border)] p-3">
    <summary className="cursor-pointer text-sm">学习时间容量</summary>
    {query.isPending ? <p>正在读取容量…</p> : query.isError
      ? <p role="alert">容量暂时无法读取。</p>
      : <CapacitySummary days={day ? [day] : []} />}
    <label className="my-2 flex flex-wrap items-center gap-2 text-sm">
      {date} 每日学习上限（分钟）
      <input type="number" min="0" max="1440" step="1" value={minutes}
        onChange={event => setMinutes(event.target.value)}
        className="w-24 rounded border border-[var(--border)] px-2 py-1" />
    </label>
    <p className="text-xs text-[var(--foreground-muted)]">保存后将校验当天所有活跃计划。留空可清除上限。</p>
    <button type="button" disabled={save.isPending} onClick={() => save.mutate()} className="mt-2 text-sm text-[var(--accent)]">
      {save.isPending ? "保存中…" : "保存学习上限"}
    </button>
    {save.error && <p role="alert">{save.error.message}</p>}
    {save.isSuccess && <p role="status">已保存学习上限。</p>}
  </details>;
}
