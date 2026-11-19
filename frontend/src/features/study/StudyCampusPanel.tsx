import { useQuery } from "@tanstack/react-query";
import { CheckSquare } from "@phosphor-icons/react";

import { listStudyPlans } from "../../api/study";

const campusDate = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" });
export function StudyCampusPanel() {
  const today = campusDate.format(new Date());
  const plans = useQuery({ queryKey: ["study", "plans"], queryFn: listStudyPlans });
  const agenda = (plans.data?.plans ?? [])
    .filter((plan) => plan.status === "active")
    .flatMap((plan) => plan.tasks.filter((task) =>
      task.scheduled_date >= today && task.status !== "completed" && task.status !== "skipped"))
    .sort((left, right) => left.scheduled_date.localeCompare(right.scheduled_date))
    .slice(0, 5);

  return (
    <div className="space-y-4 text-sm">
      <section aria-labelledby="campus-agenda" className="rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-4">
        <h3 id="campus-agenda" className="flex items-center gap-2 text-base font-semibold">
          <CheckSquare size={20} aria-hidden /> 学习日程
        </h3>
        {agenda.length ? (
          <ul className="mt-3 divide-y divide-[var(--border)]">
            {agenda.map((task) => (
              <li key={task.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
                <time dateTime={task.scheduled_date} className="text-xs tabular-nums text-[var(--foreground-muted)]">
                  {task.scheduled_date}
                </time>
                <strong className="min-w-0 break-words font-medium">{task.title}</strong>
              </li>
            ))}
          </ul>
        ) : (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            {plans.isError ? "暂时无法读取 HoneyOS 学习计划" : plans.isPending ? "正在读取学习计划…" : "学习计划暂无近期待办"}
          </p>
        )}
      </section>
    </div>
  );
}
