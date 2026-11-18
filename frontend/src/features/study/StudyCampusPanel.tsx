import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarBlank, CheckSquare, GraduationCap, SignIn } from "@phosphor-icons/react";

import { profilePrefix, requestJson } from "../../api/client";
import { listStudyPlans } from "../../api/study";

const categories = [
  ["近期考试", "考试日期、时间、考场"],
  ["成绩", "各学期课程成绩与学分"],
  ["学习通", "课程任务、作业截止时间和测验"],
  ["校历与通知", "教学周、学校日程与教务通知"],
  ["综测", "综合测评进度与结果"],
  ["第二课堂", "活动、学分与认定记录"],
  ["宿舍用电", "剩余电费和用电记录"],
  ["洗衣房", "设备可用状态"],
] as const;

function localDay(date: Date): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" }).format(date);
}

function initialRange() {
  const now = Date.now();
  return { start: localDay(new Date(now)), end: localDay(new Date(now + 13 * 86_400_000)) };
}

export function StudyCampusPanel() {
  const [range, setRange] = useState(initialRange);
  const today = localDay(new Date());
  const preference = `honeyos.campus.connected:${profilePrefix()}`;
  const loaded = useRef(false);
  const plans = useQuery({ queryKey: ["study", "plans"], queryFn: listStudyPlans });
  const agenda = (plans.data?.plans ?? []).filter((plan) => plan.status === "active")
    .flatMap((plan) => plan.tasks.filter((task) => task.scheduled_date >= today && !["completed", "skipped"].includes(task.status)))
    .sort((a, b) => a.scheduled_date.localeCompare(b.scheduled_date)).slice(0, 5);
  const calendar = useMutation({
    mutationFn: (selected: typeof range & { interactive?: boolean }) => requestJson<{ days: Record<string, string[]> }>("/api/study/campus/calendar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selected),
    }),
    onSuccess: () => localStorage.setItem(preference, "yes"),
  });
  const sync = calendar.mutate;
  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    if (localStorage.getItem(preference) === "yes") sync(initialRange());
  }, [preference, sync]);
  const days = Object.entries(calendar.data?.days ?? {}).sort(([left], [right]) => left.localeCompare(right));
  const todayClasses = calendar.data?.days[today];

  return (
    <div className="space-y-5 text-sm">
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">校园账号</h3>
            <p className="mt-1 text-xs text-[var(--foreground-muted)]">在重医认证页面输入密码，登录后返回这里刷新。</p>
          </div>
          <button type="button" disabled={calendar.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-3 py-2 font-medium text-white disabled:opacity-50"
            onClick={() => sync({ ...initialRange(), interactive: true })}>
            <SignIn size={17} /> {calendar.isPending ? "正在连接…" : "连接校园账号"}
          </button>
        </div>
        {calendar.error ? <p role="alert" className="mt-2 text-xs">{calendar.error.message}</p> : null}
      </section>
      <section aria-labelledby="campus-calendar" className="space-y-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-4">
        <div>
          <h3 id="campus-calendar" className="flex items-center gap-2 text-base font-semibold"><CalendarBlank size={20} /> 今日课程</h3>
          <time className="text-xs text-[var(--foreground-muted)]" dateTime={today}>{today}</time>
        </div>
        {todayClasses?.length ? (
          <ul className="grid gap-2">
            {todayClasses.map((entry, index) => <li key={index} className="whitespace-pre-line break-words rounded-r-lg border-l-2 border-l-[var(--accent)] bg-[var(--surface)] p-3">{entry}</li>)}
          </ul>
        ) : <p className="text-xs text-[var(--foreground-muted)]">{todayClasses ? "今日无课" : "今日课表尚未同步"}</p>}
        <details>
        <summary className="cursor-pointer text-xs font-medium">查看其他日期或刷新课表</summary>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => {
          event.preventDefault();
          calendar.mutate(range);
        }}>
          <label className="grid gap-1 text-xs">开始日期
            <input type="date" required value={range.start} max={range.end}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-2"
              onChange={(event) => setRange({ ...range, start: event.target.value })} />
          </label>
          <label className="grid gap-1 text-xs">结束日期
            <input type="date" required value={range.end} min={range.start}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-2"
              onChange={(event) => setRange({ ...range, end: event.target.value })} />
          </label>
          <button type="submit" disabled={calendar.isPending}
            className="rounded-lg bg-[var(--accent)] px-3 py-2 font-medium text-white disabled:opacity-50">
            {calendar.isPending ? "正在连接…" : calendar.data ? "刷新课表" : "连接 / 刷新课表"}
          </button>
        </form>
        {days.length ? (
          <div className="space-y-3" aria-live="polite">
            <p className="text-xs text-[var(--foreground-muted)]">来源：重医教务系统。只展示教务页面中已确认的日期。</p>
            {days.map(([day, entries]) => (
              <div key={day} className="border-t border-[var(--border)] pt-2">
                <h4 className="font-medium"><time dateTime={day}>{day}</time></h4>
                {entries.length ? (
                  <ul className="mt-1 grid gap-2">
                    {entries.map((entry, index) => <li key={index} className="whitespace-pre-line break-words rounded-lg bg-[var(--surface)] p-2">{entry}</li>)}
                  </ul>
                ) : <p className="mt-1 text-xs text-[var(--foreground-muted)]">无课</p>}
              </div>
            ))}
          </div>
        ) : null}
        </details>
      </section>

      <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-4">
        <h3 className="flex items-center gap-2 text-base font-semibold"><CheckSquare size={20} /> 学习日程</h3>
        {agenda.length ? (
          <ul className="mt-3 divide-y divide-[var(--border)]">
            {agenda.map((task) => <li key={task.id} className="flex flex-wrap items-baseline gap-2 py-2">
              <time dateTime={task.scheduled_date} className="text-xs text-[var(--foreground-muted)]">{task.scheduled_date}</time>
              <strong className="font-medium">{task.title}</strong>
            </li>)}
          </ul>
        ) : <p className="mt-2 text-xs text-[var(--foreground-muted)]">{plans.isError ? "暂时无法读取 Honey 学习计划" : plans.isPending ? "正在读取 Honey 学习计划…" : "Honey 学习计划暂无待办"}</p>}
      </section>
      <section aria-labelledby="campus-sources">
        <h3 id="campus-sources" className="flex items-center gap-2 font-semibold"><GraduationCap size={20} /> 校园服务</h3>
        <ul className="mt-2 grid gap-2 sm:grid-cols-2">
          {categories.map(([name, description]) => (
            <li key={name} className="rounded-xl border border-[var(--border)] p-3">
              <div className="flex items-baseline justify-between gap-2">
                <strong>{name}</strong>
                <span className="text-xs text-[var(--foreground-muted)]">待接入</span>
              </div>
              <p className="mt-1 text-xs text-[var(--foreground-muted)]">{description}</p>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
