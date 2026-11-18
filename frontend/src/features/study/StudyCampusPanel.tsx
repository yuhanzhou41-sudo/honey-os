import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { requestJson } from "../../api/client";

const categories = [
  ["考试", "考试日期、时间、考场"],
  ["成绩", "各学期课程成绩与学分"],
  ["课程与作业", "学习通、网络教学平台的课程、任务和资料"],
  ["校历与通知", "教学周、学校日程与教务通知"],
  ["综测", "综合测评进度与结果"],
  ["第二课堂", "活动、学分与认定记录"],
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
  const calendar = useMutation({
    mutationFn: (selected: typeof range) => requestJson<{ days: Record<string, string[]> }>("/api/study/campus/calendar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(selected),
    }),
  });
  const days = Object.entries(calendar.data?.days ?? {}).sort(([left], [right]) => left.localeCompare(right));

  return (
    <div className="space-y-5 text-sm">
      <section aria-labelledby="campus-calendar" className="space-y-3 rounded-xl border border-[var(--border)] p-4">
        <div>
          <h3 id="campus-calendar" className="font-semibold">我的课表</h3>
          <p className="mt-1 text-xs text-[var(--foreground-muted)]">
            首次连接时，在校园专用 Edge 完成学校认证，再回这里刷新。Honey 会复用这个浏览器的登录状态；学校要求重新验证时才需要再次登录。
          </p>
        </div>
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
        {calendar.error ? <p role="alert" className="text-xs">{calendar.error.message}</p> : null}
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
      </section>

      <section aria-labelledby="campus-sources">
        <h3 id="campus-sources" className="font-semibold">其他校园内容</h3>
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
