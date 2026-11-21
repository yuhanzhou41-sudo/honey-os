import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getPlanReminder,
  setPlanReminder,
  type PlanReminderSettings,
  type ReminderMode,
} from "../../api/study-planning";

const modeOrder: ReminderMode[] = ["gentle", "standard", "strong", "custom"];
const card = "mt-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4";
const field = "rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-2 py-1 text-sm";
const plainButton = "rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-1.5 text-sm";

export default function StudyReminderPanel({ planId }: { planId: string }) {
  const client = useQueryClient();
  const queryKey = ["study-plan-reminder", planId];
  const saved = useQuery({ queryKey, queryFn: () => getPlanReminder(planId), retry: false });
  const [draft, setDraft] = useState<PlanReminderSettings>();

  useEffect(() => {
    setDraft(undefined);
  }, [planId]);

  const mutation = useMutation({
    mutationFn: (value: PlanReminderSettings) => setPlanReminder(planId, value),
    onSuccess: (data) => {
      client.setQueryData(queryKey, data);
      setDraft(undefined);
    },
  });

  if (saved.isLoading) {
    return <section className={card}><p className="text-sm">正在读取学习提醒…</p></section>;
  }
  const summary = saved.data;
  if (!summary) {
    return (
      <section className={card}>
        <h2 className="text-sm font-medium">学习提醒</h2>
        <p className="mt-1 text-xs text-red-500">提醒设置暂时无法读取。</p>
      </section>
    );
  }

  const settings = draft ?? summary.settings;
  const presets = summary.presets;
  const times = settings.times.length ? settings.times : presets[settings.mode].times;
  const update = (patch: Partial<PlanReminderSettings>) => setDraft({ ...settings, ...patch });
  const pickMode = (mode: ReminderMode) => {
    update({
      mode,
      times: mode === "custom" ? (times.length ? times : ["20:00"]) : presets[mode].times,
    });
  };
  const setTime = (index: number, value: string) => {
    const next = [...times];
    next[index] = value;
    update({ times: next });
  };
  const save = () => mutation.mutate({
    ...settings,
    times: times.map((time) => time.trim()).filter(Boolean),
  });

  return (
    <section className={card}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">学习提醒</h2>
          <p className="mt-1 text-xs text-[var(--foreground-muted)]">
            到点弹出 Windows 系统通知；内容由本机 Qwen 结合当天计划生成，语气从轻松逐步转为急迫。
          </p>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={settings.enabled}
            disabled={mutation.isPending}
            onChange={(event) => update({ enabled: event.target.checked })}
          />
          开启系统提醒
        </label>
      </div>

      <div className="mt-3 flex flex-wrap gap-2" role="radiogroup" aria-label="提醒强度">
        {modeOrder.map((mode) => (
          <button
            key={mode}
            type="button"
            role="radio"
            aria-checked={settings.mode === mode}
            className={
              "rounded-[var(--radius-md)] border px-3 py-1.5 text-sm " +
              (settings.mode === mode
                ? "border-[var(--accent)] text-[var(--accent)]"
                : "border-[var(--border-strong)] bg-[var(--surface)]")
            }
            onClick={() => pickMode(mode)}
          >
            {presets[mode].label}
            {mode !== "custom" && (
              <span className="ml-1 text-xs text-[var(--foreground-muted)]">
                每天 {presets[mode].times.length} 次
              </span>
            )}
          </button>
        ))}
      </div>

      {settings.mode === "custom" ? (
        <div className="mt-3 space-y-2">
          {times.map((time, index) => (
            <div key={index} className="flex items-center gap-2 text-sm">
              <input
                type="time"
                aria-label={"第 " + (index + 1) + " 次提醒时间"}
                className={field}
                value={time}
                onChange={(event) => setTime(index, event.target.value)}
              />
              <button
                type="button"
                className="text-xs text-[var(--foreground-muted)]"
                onClick={() => update({ times: times.filter((_, i) => i !== index) })}
              >
                删除
              </button>
            </div>
          ))}
          {times.length < 6 && (
            <button
              type="button"
              className="text-xs underline"
              onClick={() => update({ times: [...times, "20:00"] })}
            >
              ＋ 添加时间点
            </button>
          )}
        </div>
      ) : (
        <p className="mt-3 text-sm">每天提醒时间：{times.join("、")}</p>
      )}

      <div className="mt-3 space-y-1 text-xs text-[var(--foreground-muted)]">
        <p>已提醒 {summary.sent_total} 次 · 今日 {summary.sent_today} 次</p>
        <p>第 1 次轻松，第 2 次紧张，之后急迫；计划完成后自动停止。</p>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" className={plainButton} disabled={mutation.isPending} onClick={save}>
          {mutation.isPending ? "保存中…" : "保存提醒"}
        </button>
        {mutation.isSuccess && !mutation.isPending && <span role="status" className="text-xs">已保存。</span>}
        {mutation.error && (
          <span role="alert" className="text-xs text-red-500">{(mutation.error as Error).message}</span>
        )}
      </div>
    </section>
  );
}
