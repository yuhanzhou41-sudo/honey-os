import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarBlank, CheckSquare, GraduationCap, Student } from "@phosphor-icons/react";

import {
  getCampusExams,
  getCampusGrades,
  getCampusTimetable,
  refreshCampusExams,
  refreshCampusGrades,
  refreshCampusTimetable,
} from "../../api/campus";
import { listStudyPlans } from "../../api/study";

const campusDate = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" });
const campusWeekday = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  weekday: "short",
});

export function todayWeekdayLabel(now: Date = new Date()): string {
  return campusWeekday.format(now);
}

export function extractExamDate(value: string): string | null {
  const match = value.match(/(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (!match) return null;
  return `${match[1]}-${match[2].padStart(2, "0")}-${match[3].padStart(2, "0")}`;
}

export function examCountdown(examDate: string, now: Date = new Date()): number | null {
  const iso = extractExamDate(examDate);
  if (!iso) return null;
  const today = campusDate.format(now);
  return Math.round(
    (Date.parse(`${iso}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / 86_400_000,
  );
}

function countdownLabel(days: number | null): string {
  if (days === null) return "未排期";
  if (days < 0) return "已结束";
  if (days === 0) return "今天";
  if (days === 1) return "明天";
  return `${days} 天后`;
}

function formatCaptured(capturedAt: string | null): string {
  if (!capturedAt) return "未知时间";
  return capturedAt.slice(0, 16).replace("T", " ");
}

export function StudyCampusPanel() {
  const today = campusDate.format(new Date());
  const weekday = todayWeekdayLabel();
  const queryClient = useQueryClient();
  const plans = useQuery({ queryKey: ["study", "plans"], queryFn: listStudyPlans });
  const examsQuery = useQuery({ queryKey: ["campus", "exams"], queryFn: getCampusExams });
  const timetableQuery = useQuery({ queryKey: ["campus", "timetable"], queryFn: getCampusTimetable });
  const gradesQuery = useQuery({ queryKey: ["campus", "grades"], queryFn: getCampusGrades });
  const refresh = useMutation({
    mutationFn: refreshCampusExams,
    onSuccess: (data) => queryClient.setQueryData(["campus", "exams"], data),
  });
  const refreshTimetable = useMutation({
    mutationFn: refreshCampusTimetable,
    onSuccess: (data) => queryClient.setQueryData(["campus", "timetable"], data),
  });
  const refreshGrades = useMutation({
    mutationFn: refreshCampusGrades,
    onSuccess: (data) => queryClient.setQueryData(["campus", "grades"], data),
  });
  const exams = examsQuery.data?.exams;
  const timetable = timetableQuery.data?.timetable;
  const grades = gradesQuery.data?.grades;
  const todayCourses = (timetable?.records ?? []).filter((record) => record.day === weekday);
  const agenda = (plans.data?.plans ?? [])
    .filter((plan) => plan.status === "active")
    .flatMap((plan) => plan.tasks.filter((task) =>
      task.scheduled_date >= today && task.status !== "completed" && task.status !== "skipped"))
    .sort((left, right) => left.scheduled_date.localeCompare(right.scheduled_date))
    .slice(0, 5);

  return (
    <div className="space-y-4 text-sm">
      <section aria-labelledby="campus-timetable" className="rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-4">
        <div className="flex items-center justify-between gap-2">
          <h3 id="campus-timetable" className="flex items-center gap-2 text-base font-semibold">
            <Student size={20} aria-hidden /> 今日课程
            <span className="text-xs font-normal text-[var(--foreground-muted)]">{weekday}</span>
          </h3>
          <button
            type="button"
            onClick={() => refreshTimetable.mutate()}
            disabled={refreshTimetable.isPending}
            aria-label="刷新课表"
            className="text-xs text-[var(--foreground-muted)] disabled:opacity-50"
          >
            {refreshTimetable.isPending ? "刷新中…" : "刷新"}
          </button>
        </div>
        {timetableQuery.isError ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            暂时无法读取校园课表数据。
          </p>
        ) : timetableQuery.isPending ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            正在读取校园课表数据…
          </p>
        ) : timetable && timetable.needs_capture ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            尚未采集课表数据：请在宿主中完成官方登录并打开「我的课表」，然后点刷新。
          </p>
        ) : timetable && todayCourses.length === 0 ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            今天没有课。
          </p>
        ) : timetable ? (
          <>
            <ul className="mt-3 divide-y divide-[var(--border)]">
              {todayCourses.map((record) => (
                <li key={record.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
                  {record.period && (
                    <span className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-xs tabular-nums">
                      {record.period}
                    </span>
                  )}
                  <strong className="min-w-0 break-words font-medium">{record.detail}</strong>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-[var(--foreground-muted)]">
              来源 {timetable.source ?? "未知"} · 采集于 {formatCaptured(timetable.captured_at)}
              {timetable.stale ? "（缓存已过期，请刷新）" : ""}
            </p>
          </>
        ) : null}
        {refreshTimetable.data?.timetable?.message && (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            {refreshTimetable.data.timetable.message}
          </p>
        )}
      </section>

      <section aria-labelledby="campus-exams" className="rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-4">
        <div className="flex items-center justify-between gap-2">
          <h3 id="campus-exams" className="flex items-center gap-2 text-base font-semibold">
            <CalendarBlank size={20} aria-hidden /> 近期考试
          </h3>
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            aria-label="刷新考试"
            className="text-xs text-[var(--foreground-muted)] disabled:opacity-50"
          >
            {refresh.isPending ? "刷新中…" : "刷新"}
          </button>
        </div>
        {examsQuery.isError ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            暂时无法读取校园考试数据。
          </p>
        ) : examsQuery.isPending ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            正在读取校园考试数据…
          </p>
        ) : exams && exams.needs_capture ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            尚未采集考试数据：请在宿主中完成官方登录并进入考试查询页捕获，然后点刷新。
          </p>
        ) : exams && exams.row_count === 0 ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            学校当前没有已安排的考试。
          </p>
        ) : exams ? (
          <>
            <ul className="mt-3 divide-y divide-[var(--border)]">
              {exams.records.map((record) => {
                const days = examCountdown(record.exam_date);
                return (
                  <li key={record.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
                    <span className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-xs tabular-nums">
                      {countdownLabel(days)}
                    </span>
                    <strong className="min-w-0 break-words font-medium">{record.course}</strong>
                    <time className="text-xs tabular-nums text-[var(--foreground-muted)]">
                      {record.exam_date}
                    </time>
                    {record.arrangement && (
                      <span className="text-xs text-[var(--foreground-muted)]">{record.arrangement}</span>
                    )}
                    {record.location && (
                      <span className="text-xs text-[var(--foreground-muted)]">{record.location}</span>
                    )}
                  </li>
                );
              })}
            </ul>
            <p className="mt-2 text-xs text-[var(--foreground-muted)]">
              来源 {exams.source ?? "未知"} · 采集于 {formatCaptured(exams.captured_at)}
              {exams.stale ? "（缓存已过期，请刷新）" : ""}
            </p>
          </>
        ) : null}
        {refresh.data?.exams?.message && (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            {refresh.data.exams.message}
          </p>
        )}
      </section>

      <section aria-labelledby="campus-grades" className="rounded-2xl border border-[var(--border)] bg-[var(--surface-raised)] p-4">
        <div className="flex items-center justify-between gap-2">
          <h3 id="campus-grades" className="flex items-center gap-2 text-base font-semibold">
            <GraduationCap size={20} aria-hidden /> 成绩
            {grades && grades.row_count > 0 && (
              <span className="text-xs font-normal text-[var(--foreground-muted)]">
                {grades.row_count} 门
              </span>
            )}
          </h3>
          <button
            type="button"
            onClick={() => refreshGrades.mutate()}
            disabled={refreshGrades.isPending}
            aria-label="刷新成绩"
            className="text-xs text-[var(--foreground-muted)] disabled:opacity-50"
          >
            {refreshGrades.isPending ? "刷新中…" : "刷新"}
          </button>
        </div>
        {gradesQuery.isError ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            暂时无法读取校园成绩数据。
          </p>
        ) : gradesQuery.isPending ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            正在读取校园成绩数据…
          </p>
        ) : grades && grades.needs_capture ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            尚未采集成绩数据：请在宿主中完成官方登录并打开成绩查询页，然后点刷新。
          </p>
        ) : grades && grades.row_count === 0 ? (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            学校当前没有可显示的成绩记录。
          </p>
        ) : grades ? (
          <>
            <ul className="mt-3 divide-y divide-[var(--border)]">
              {grades.records.slice(0, 8).map((record) => (
                <li key={record.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
                  <strong className="min-w-0 break-words font-medium">{record.course}</strong>
                  <span className="rounded-full bg-[var(--surface)] px-2 py-0.5 text-xs tabular-nums">
                    {record.score || "—"}
                  </span>
                  {record.credit && (
                    <span className="text-xs text-[var(--foreground-muted)]">{record.credit} 学分</span>
                  )}
                  {record.term && (
                    <span className="text-xs text-[var(--foreground-muted)]">{record.term}</span>
                  )}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs text-[var(--foreground-muted)]">
              来源 {grades.source ?? "未知"} · 采集于 {formatCaptured(grades.captured_at)}
              {grades.stale ? "（缓存已过期，请刷新）" : ""}
            </p>
          </>
        ) : null}
        {refreshGrades.data?.grades?.message && (
          <p role="status" className="mt-2 text-xs text-[var(--foreground-muted)]">
            {refreshGrades.data.grades.message}
          </p>
        )}
      </section>

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
