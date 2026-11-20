import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { StudyPlan } from "../../api/study";
import { confirmChatStudyPlan, confirmManualStudyChange, previewChatStudyPlan } from "../../api/study-planning";
import {
  assignActivity, getActivities, getGrowth, getLearningDay, getLearningWeek, getRewardLedger,
  getSupervision, growthAction, setSupervision,
  type Closure, type FlexPreview, type GrowthState, type SupervisionSettings,
} from "../../api/study-growth";
import { useHoneyStore } from "../../runtime/honey-store";

const levels: Record<string,string> = { full: "全部完成", standard: "达到标准", minimum: "完成保底", incomplete: "尚未完成", no_tasks: "无任务" };

export default function StudyGrowthPanel({ plan, onChanged }: { plan?: StudyPlan; onChanged: () => void }) {
  const client = useQueryClient();
  const sessionId = useHoneyStore(state => state.sessionId);
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState("");
  const [taskId, setTaskId] = useState("");
  const [slotId, setSlotId] = useState("");
  const [flexMinutes, setFlexMinutes] = useState(15);
  const [eventId, setEventId] = useState("");
  const [output, setOutput] = useState("");
  const [notice, setNotice] = useState("");
  const growth = useQuery({ queryKey: ["study-growth", plan?.id, plan?.updated_at],
    queryFn: () => getGrowth(plan!.id), enabled: Boolean(plan), retry: false, refetchInterval: 30_000 });
  const activities = useQuery({ queryKey: ["study-activities"], queryFn: getActivities, enabled: open, retry: false });
  const supervision = useQuery({ queryKey: ["study-supervision"], queryFn: getSupervision, enabled: open, retry: false });
  const [settings, setSettings] = useState<SupervisionSettings>();
  const activeSettings = settings ?? supervision.data;
  const action = useMutation({
    mutationFn: async (run: () => Promise<void>) => { setNotice(""); await run(); },
    onError: async () => { await client.invalidateQueries({ queryKey: ["study-growth"] }); onChanged(); },
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["study-growth"] });
      await client.invalidateQueries({ queryKey: ["study-activities"] });
      await client.invalidateQueries({ queryKey: ["study-supervision"] });
      onChanged(); setNotice("已更新。");
    },
  });
  if (!plan) return null;
  const state = growth.data;
  const today = new Date().toLocaleDateString("en-CA");
  const day = date || (today >= plan.start_date && today <= plan.end_date ? today : plan.start_date);
  const config = state?.settings ?? { timezone: "Asia/Shanghai", minimum_mode: false };
  const run = (fn: () => Promise<void>) => action.mutate(fn);
  const field = "rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1";

  return <section className="mt-5 rounded border border-[var(--border)] p-4">
    <div className="flex flex-wrap gap-6 text-sm">
      <p>阳光点 <strong>{state ? state.sunlight : "—"}</strong></p>
      <p>小花盆 <span aria-hidden="true">{({ 种子: "🫘", 发芽: "🌱", 幼苗: "🌱", 长叶: "🌿", 花苞: "🌷" } as Record<string,string>)[state?.plant ?? "种子"]}</span> <strong>{state?.plant ?? "—"}</strong></p>
      {state?.enabled && <p>标准学习日 {state.standard_days} · 学习势能 {state.momentum}</p>}
    </div>
    {state?.final_summary && <p className="mt-2">{state.final_summary}</p>}
    {plan.schema_version === 1 && <button className="mt-2 text-sm text-[var(--accent)]" onClick={() => run(async () => { await confirmManualStudyChange(plan.id, { schema_version: 2 }); })}>预览升级为V2任务属性</button>}
    {growth.isError && <p role="alert">成长记录暂时无法读取。</p>}
    {state && !state.enabled && <button className="mt-3 text-[var(--accent)]" disabled={action.isPending}
      onClick={() => run(async () => { await growthAction<GrowthState>(plan.id, "enable", config); })}>启用本计划成长记录</button>}
    <details className="mt-3" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-sm">保底、机动与学习记忆</summary>
      <fieldset disabled={action.isPending} className="mt-3 space-y-3 text-sm">
        <label className="flex gap-2"><input type="checkbox" checked={Boolean(config.minimum_mode)} disabled={!state?.enabled}
          onChange={event => run(async () => { await growthAction(plan.id, "enable", { ...config, minimum_mode: event.target.checked }); })} />
          开启今日低状态保底模式</label>
        <label>查看日期 <input type="date" className={field} value={day} onChange={event => setDate(event.target.value)} /></label>
        {state?.days.filter(item => item.date === day).map(item => <p key={item.date}>
          {levels[item.level]} · {item.completed}/{item.tasks} · 专注 {item.focus_minutes} 分钟
        </p>)}
        <div className="flex flex-wrap gap-3">
          <button onClick={() => run(async () => { const snapshot = await getLearningDay(plan.id, day); setOutput(String(snapshot.date) + " · 完成 " + snapshot.completed + "/" + snapshot.tasks + " · 专注 " + snapshot.focus_minutes + " 分钟\n练习 " + snapshot.attempts + " 次 · 答对 " + snapshot.correct + " 次 · 闪卡复述 " + snapshot.recalls + " 次\n当日阳光 " + snapshot.reward_points + " · 花盆 " + snapshot.plant); })}>查看每日学习记忆</button>
          <button onClick={() => run(async () => {
            const ledger = await getRewardLedger(plan.id);
            const labels: Record<string,string> = { daily: "每日达标", stage: "阶段奖励", attempt: "答题", recall: "闪卡", focus: "专注" };
            setOutput(ledger.entries.map(entry => entry.created_at + " · " + (labels[entry.source.split(":")[0]] ?? "学习") + " · " + (entry.amount > 0 ? "+" : "") + entry.amount + " 阳光").join("\n") || "暂无奖励流水。");
          })}>查看阳光明细</button>
          <button onClick={() => run(async () => {
            const report = await getLearningWeek(plan.id, day); setOutput(report.body ?? report.final?.summary ?? "");
          })}>查看本周评价</button>
          <button onClick={() => run(async () => {
            const proposal = await growthAction<{ markdown: string }>(plan.id, "recovery", { date: day });
            const draft = { markdown: proposal.markdown, revision: true };
            const preview = await previewChatStudyPlan(draft);
            if (window.confirm(preview.plan.tasks.map(task => task.title + " · " + task.scheduled_date).join("\n") + "\n确认仅调整本次恢复任务？"))
              await confirmChatStudyPlan(draft, preview);
          })}>预览延期恢复</button>
        </div>
        {plan.schema_version === 2 && <div className="flex flex-wrap items-center gap-2">
          <label>新增机动分钟 <input className={field} type="number" min="1" max="1440" value={flexMinutes} onChange={event => setFlexMinutes(Number(event.target.value))} /></label>
          <button onClick={() => run(async () => {
            if (!Number.isInteger(flexMinutes) || flexMinutes < 1 || flexMinutes > 1440) throw new Error("请输入1至1440的整数分钟。");
            await confirmManualStudyChange(plan.id, { flex_slots: [...(plan.flex_slots ?? []), {
              id: "flex_" + crypto.randomUUID().replaceAll("-", ""), scheduled_date: day, planned_minutes: flexMinutes,
            }] });
          })}>预览添加机动时间</button>
        </div>}
        <div className="flex flex-wrap gap-2">
          <select aria-label="机动调整任务" className={field} value={taskId} onChange={event => setTaskId(event.target.value)}>
            <option value="">选择未完成任务</option>
            {plan.tasks.filter(task => task.status !== "completed").map(task => <option key={task.id} value={task.id}>{task.title} · {task.scheduled_date}</option>)}
          </select>
          <select aria-label="机动时间槽" className={field} value={slotId} onChange={event => setSlotId(event.target.value)}>
            <option value="">选择机动时间</option>
            {plan.flex_slots?.map(slot => <option key={slot.id} value={slot.id}>{slot.scheduled_date} · {slot.planned_minutes}分钟</option>)}
          </select>
          <button disabled={!taskId || !slotId} onClick={() => run(async () => {
            const body = { task_id: taskId, slot_id: slotId };
            const preview = await growthAction<FlexPreview>(plan.id, "flex-preview", body);
            if (window.confirm(preview.plan.tasks.map(task => task.title + " · " + task.scheduled_date).join("\n") + "\n确认使用机动时间？"))
              await growthAction(plan.id, "flex-confirm", { ...body, expected_updated_at: preview.expected_updated_at, request_id: crypto.randomUUID() });
          })}>预览使用机动</button>
        </div>
        {state?.history?.filter(item => item.active).map(item => <p key={item.request_id}>
          {item.old_date} → {item.new_date} · {item.minutes}分钟{" "}
          <button onClick={() => run(async () => {
            if (window.confirm("确认撤销这次机动调整？"))
              await growthAction(plan.id, "flex-undo", { request_id: item.request_id, expected_updated_at: plan.updated_at });
          })}>撤销机动</button>
        </p>)}
        <div className="flex flex-wrap gap-2">
          <select aria-label="学习事件归属" className={field} value={eventId} onChange={event => setEventId(event.target.value)}>
            <option value="">选择最近的答题或闪卡事件</option>
            {activities.data?.events.map(event => <option key={event.kind + event.id} value={event.kind + ":" + event.id}>
              {event.kind === "attempt" ? "答题" : "闪卡"} · {event.created_at} · {event.plan_id ? "已分配" : "未分配"} · {event.summary?.slice(0,60) ?? event.id}
            </option>)}
          </select>
          <button disabled={!eventId} onClick={() => run(async () => {
            const event = activities.data?.events.find(item => item.kind + ":" + item.id === eventId);
            if (event && window.confirm("确认将这次真实学习事件归入当前计划？")) await assignActivity(event, plan.id);
          })}>归入当前计划</button>
          <button disabled={!eventId} onClick={() => run(async () => {
            const event = activities.data?.events.find(item => item.kind + ":" + item.id === eventId);
            if (event && window.confirm("确认将此事件改为未分配？")) await assignActivity(event, null);
          })}>改为未分配</button>
        </div>
        <div className="flex gap-3">
          {(["completed", "stopped"] as const).map(reason => <button key={reason} onClick={() => run(async () => {
            const preview = await growthAction<Closure>(plan.id, "close-preview", { reason });
            if (!preview.expected_updated_at || !preview.facts_revision) { setOutput(preview.summary); return; }
            if (window.confirm(preview.summary + "\n确认结束并清理本计划过往周报正文？"))
              await growthAction(plan.id, "close-confirm", { ...preview, reason });
          })}>{reason === "completed" ? "完成并归档" : "停止并归档"}</button>)}
        </div>
      </fieldset>
      {output && <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap text-xs">{output}</pre>}
      {activeSettings && <fieldset disabled={action.isPending} className="mt-4 space-y-2 text-sm">
        <legend>学习主动监督</legend>
        <label className="flex gap-2"><input type="checkbox" checked={activeSettings.enabled} onChange={event =>
          setSettings({ ...activeSettings, enabled: event.target.checked })} />授权在当前聊天主动发送学习提醒</label>
        <label>提醒时间（小时） <input className={field} type="number" min="0" max="23" value={activeSettings.remind_hour}
          onChange={event => setSettings({ ...activeSettings, remind_hour: Number(event.target.value) })} /></label>
        <label>安静时段 <input aria-label="安静开始小时" className={field} type="number" min="0" max="23" value={activeSettings.quiet_start}
          onChange={event => setSettings({ ...activeSettings, quiet_start: Number(event.target.value) })} /> 至{" "}
          <input aria-label="安静结束小时" className={field} type="number" min="0" max="23" value={activeSettings.quiet_end}
          onChange={event => setSettings({ ...activeSettings, quiet_end: Number(event.target.value) })} /></label>
        <p>按 {activeSettings.timezone} 计算，每天最多一次，多个计划合并；专注中暂停提醒。</p>
        <button onClick={() => run(async () => { setSettings(await setSupervision({
          ...activeSettings, session_id: sessionId ?? activeSettings.session_id,
        })); })}>保存监督设置</button>
      </fieldset>}
    </details>
    {action.isPending && <p role="status">正在处理…</p>}
    {notice && <p role="status">{notice}</p>}
    {action.error && <p role="alert">{action.error.message}</p>}
  </section>;
}
