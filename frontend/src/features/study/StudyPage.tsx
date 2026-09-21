import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  abandonStudySession,
  completeStudySession,
  createStudyPlan,
  createStudySession,
  createStudyTask,
  deleteStudyPlan,
  deleteStudyTask,
  getStudyPomodoroState,
  listStudyPlans,
  listStudySessions,
  pauseStudySession,
  resumeStudySession,
  setStudyTaskStatus,
  startStudySession,
  updateStudyPlan,
  type StudyPlan,
  type StudyPomodoroState,
  type StudySession,
  type StudyTask,
  type StudyTaskStatus,
} from "../../api/study";
import { PageHeader } from "../../components/honey/PageHeader";
import { ErrorState, LoadingState } from "../../components/honey/PageState";

const plansKey = ["study", "plans"] as const;

export function StudyPage() {
  const qc = useQueryClient();
  const plansQuery = useQuery({ queryKey: plansKey, queryFn: listStudyPlans });
  const plans = plansQuery.data?.plans ?? [];

  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [newPlanTitle, setNewPlanTitle] = useState("");
  const [newTaskTitle, setNewTaskTitle] = useState("");

  useEffect(() => {
    if (!plans.length) {
      setSelectedPlanId("");
      return;
    }
    if (!selectedPlanId || !plans.some((plan) => plan.id === selectedPlanId)) {
      setSelectedPlanId(plans[0].id);
    }
  }, [plans, selectedPlanId]);

  const selectedPlan =
    plans.find((plan) => plan.id === selectedPlanId) ?? plans[0];

  const refreshPlans = () => qc.invalidateQueries({ queryKey: plansKey });

  const createPlan = useMutation({
    mutationFn: async () => {
      const title = newPlanTitle.trim();
      if (!title) throw new Error("请输入计划名称");
      const today = new Date();
      const start = today.toISOString().slice(0, 10);
      const endDate = new Date(today);
      endDate.setDate(endDate.getDate() + 6);
      return createStudyPlan({
        title,
        start_date: start,
        end_date: endDate.toISOString().slice(0, 10),
        focus_minutes: 25,
        break_minutes: 5,
        long_break_minutes: 15,
        long_break_after_sessions: 4,
      });
    },
    onSuccess: ({ plan }) => {
      setNewPlanTitle("");
      setSelectedPlanId(plan.id);
      refreshPlans();
    },
  });

  const createTask = useMutation({
    mutationFn: async () => {
      if (!selectedPlan) throw new Error("请先选择学习计划");
      const title = newTaskTitle.trim();
      if (!title) throw new Error("请输入任务名称");
      return createStudyTask(selectedPlan.id, {
        title,
        scheduled_date: selectedPlan.start_date,
        planned_minutes: selectedPlan.focus_minutes,
      });
    },
    onSuccess: () => {
      setNewTaskTitle("");
      refreshPlans();
    },
  });

  const deletePlanMutation = useMutation({
    mutationFn: (id: string) => deleteStudyPlan(id),
    onSuccess: refreshPlans,
  });

  const setPlanStatus = useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string;
      status: StudyPlan["status"];
    }) => updateStudyPlan(id, { status }),
    onSuccess: refreshPlans,
  });

  const setTaskStatus = useMutation({
    mutationFn: ({
      planId,
      taskId,
      status,
    }: {
      planId: string;
      taskId: string;
      status: StudyTaskStatus;
    }) => setStudyTaskStatus(planId, taskId, status),
    onSuccess: refreshPlans,
  });

  const deleteTaskMutation = useMutation({
    mutationFn: ({ planId, taskId }: { planId: string; taskId: string }) =>
      deleteStudyTask(planId, taskId),
    onSuccess: refreshPlans,
  });

  if (plansQuery.isLoading) {
    return (
      <Frame>
        <LoadingState />
      </Frame>
    );
  }

  if (plansQuery.isError) {
    return (
      <Frame>
        <ErrorState />
      </Frame>
    );
  }

  return (
    <Frame>
      <PageHeader
        title="学习"
        description="把计划放在左边，把注意力留给现在这一件事。"
      />

      <div className="mt-6 grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="min-w-0 space-y-4">
          <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4">
            <p className="text-xs font-medium uppercase tracking-[0.16em] text-[var(--foreground-muted)]">
              学习计划
            </p>

            <div className="mt-3 space-y-2">
              {plans.map((plan) => {
                const active = plan.id === selectedPlan?.id;
                return (
                  <button
                    key={plan.id}
                    onClick={() => setSelectedPlanId(plan.id)}
                    className={`w-full rounded-[var(--radius-md)] px-3 py-3 text-left transition ${
                      active
                        ? "bg-[var(--accent)] text-white"
                        : "bg-[var(--surface)] hover:bg-[var(--surface-hover)]"
                    }`}
                  >
                    <span className="block truncate text-sm font-semibold">
                      {plan.title}
                    </span>
                    <span
                      className={`mt-1 block text-xs ${
                        active ? "text-white/75" : "text-[var(--foreground-muted)]"
                      }`}
                    >
                      {plan.tasks.length} 个任务 · {planStatusText(plan.status)}
                    </span>
                  </button>
                );
              })}

              {!plans.length && (
                <p className="rounded-[var(--radius-md)] bg-[var(--surface)] px-3 py-4 text-sm text-[var(--foreground-muted)]">
                  还没有学习计划。
                </p>
              )}
            </div>

            <div className="mt-4 border-t border-[var(--border)] pt-4">
              <input
                value={newPlanTitle}
                onChange={(event) => setNewPlanTitle(event.target.value)}
                placeholder="新计划名称"
                className="w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
              />
              <button
                onClick={() => createPlan.mutate()}
                disabled={createPlan.isPending}
                className="mt-2 w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] px-3 py-2.5 text-sm font-medium disabled:opacity-50"
              >
                ＋ 新建计划
              </button>
              {createPlan.error ? (
                <p className="mt-2 text-xs text-red-500">
                  {messageOf(createPlan.error)}
                </p>
              ) : null}
            </div>
          </section>
        </aside>

        <main className="min-w-0">
          {!selectedPlan ? (
            <EmptyStudy />
          ) : (
            <PlanWorkspace
              plan={selectedPlan}
              newTaskTitle={newTaskTitle}
              onNewTaskTitle={setNewTaskTitle}
              onCreateTask={() => createTask.mutate()}
              creatingTask={createTask.isPending}
              taskError={createTask.error}
              onPlanStatus={(status) =>
                setPlanStatus.mutate({ id: selectedPlan.id, status })
              }
              onDeletePlan={() => deletePlanMutation.mutate(selectedPlan.id)}
              onTaskStatus={(taskId, status) =>
                setTaskStatus.mutate({
                  planId: selectedPlan.id,
                  taskId,
                  status,
                })
              }
              onDeleteTask={(taskId) =>
                deleteTaskMutation.mutate({
                  planId: selectedPlan.id,
                  taskId,
                })
              }
            />
          )}
        </main>
      </div>
    </Frame>
  );
}

function PlanWorkspace({
  plan,
  newTaskTitle,
  onNewTaskTitle,
  onCreateTask,
  creatingTask,
  taskError,
  onPlanStatus,
  onDeletePlan,
  onTaskStatus,
  onDeleteTask,
}: {
  plan: StudyPlan;
  newTaskTitle: string;
  onNewTaskTitle: (value: string) => void;
  onCreateTask: () => void;
  creatingTask: boolean;
  taskError: unknown;
  onPlanStatus: (status: StudyPlan["status"]) => void;
  onDeletePlan: () => void;
  onTaskStatus: (taskId: string, status: StudyTaskStatus) => void;
  onDeleteTask: (taskId: string) => void;
}) {
  const completed = plan.tasks.filter((task) => task.status === "completed").length;
  const total = plan.tasks.length;
  const progress = total ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="space-y-5">
      <section className="overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)]">
        <div className="p-5 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <StatusPill status={plan.status} />
                <span className="text-xs text-[var(--foreground-muted)]">
                  {plan.start_date} → {plan.end_date}
                </span>
              </div>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight">
                {plan.title}
              </h2>
              {plan.description ? (
                <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--foreground-muted)]">
                  {plan.description}
                </p>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-2">
              {plan.status !== "active" ? (
                <SecondaryButton onClick={() => onPlanStatus("active")}>
                  启用
                </SecondaryButton>
              ) : (
                <SecondaryButton onClick={() => onPlanStatus("paused")}>
                  暂停计划
                </SecondaryButton>
              )}
              <SecondaryButton danger onClick={onDeletePlan}>
                删除
              </SecondaryButton>
            </div>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
            <div>
              <div className="flex items-center justify-between gap-4 text-sm">
                <span className="font-medium">计划进度</span>
                <span className="text-[var(--foreground-muted)]">
                  {completed} / {total}
                </span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-[var(--surface)]">
                <div
                  className="h-full rounded-full bg-[var(--accent)] transition-[width]"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
            <div className="flex gap-4 text-xs text-[var(--foreground-muted)]">
              <span>专注 {plan.focus_minutes}m</span>
              <span>短休息 {plan.break_minutes}m</span>
              <span>
                每 {plan.long_break_after_sessions} 轮长休息 {plan.long_break_minutes}m
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4 sm:p-5">
        <div className="flex flex-wrap gap-2">
          <input
            value={newTaskTitle}
            onChange={(event) => onNewTaskTitle(event.target.value)}
            placeholder="添加今天要完成的学习任务"
            className="min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
          />
          <button
            onClick={onCreateTask}
            disabled={creatingTask}
            className="rounded-[var(--radius-md)] bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
          >
            添加任务
          </button>
        </div>
        {taskError ? (
          <p className="mt-2 text-sm text-red-500">{messageOf(taskError)}</p>
        ) : null}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">任务</h3>
          <span className="text-xs text-[var(--foreground-muted)]">
            {total ? `${total - completed} 项待完成` : "暂无任务"}
          </span>
        </div>

        <div className="space-y-3">
          {plan.tasks.map((task) => (
            <TaskRow
              key={task.id}
              plan={plan}
              task={task}
              onStatus={(status) => onTaskStatus(task.id, status)}
              onDelete={() => onDeleteTask(task.id)}
            />
          ))}

          {!plan.tasks.length && (
            <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] px-5 py-10 text-center">
              <p className="text-sm font-medium">先放进一件今天要做的事</p>
              <p className="mt-1 text-xs text-[var(--foreground-muted)]">
                添加任务后，就可以直接在任务下面启动番茄钟。
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

function TaskRow({
  plan,
  task,
  onStatus,
  onDelete,
}: {
  plan: StudyPlan;
  task: StudyTask;
  onStatus: (status: StudyTaskStatus) => void;
  onDelete: () => void;
}) {
  const done = task.status === "completed";

  return (
    <article
      className={`overflow-hidden rounded-[var(--radius-lg)] border bg-[var(--surface-raised)] ${
        done ? "border-[var(--border)] opacity-70" : "border-[var(--border)]"
      }`}
    >
      <div className="flex gap-3 p-4 sm:p-5">
        <button
          type="button"
          aria-label={done ? "标记为进行中" : "标记完成"}
          onClick={() => onStatus(done ? "in_progress" : "completed")}
          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs ${
            done
              ? "border-[var(--accent)] bg-[var(--accent)] text-white"
              : "border-[var(--border-strong)]"
          }`}
        >
          {done ? "✓" : ""}
        </button>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h4 className={`font-medium ${done ? "line-through" : ""}`}>
                {task.title}
              </h4>
              {task.description ? (
                <p className="mt-1 text-sm leading-6 text-[var(--foreground-muted)]">
                  {task.description}
                </p>
              ) : null}
              <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-[var(--foreground-muted)]">
                <span>{task.scheduled_date}</span>
                <span>{task.planned_minutes} 分钟</span>
                <span>{taskStatusText(task.status)}</span>
              </div>
            </div>

            <button
              type="button"
              onClick={onDelete}
              className="text-xs text-[var(--foreground-muted)] hover:text-red-500"
            >
              删除
            </button>
          </div>

          <PomodoroPanel plan={plan} task={task} taskCompleted={done} />
        </div>
      </div>
    </article>
  );
}

function PomodoroPanel({
  plan,
  task,
  taskCompleted,
}: {
  plan: StudyPlan;
  task: StudyTask;
  taskCompleted: boolean;
}) {
  const qc = useQueryClient();
  const sessionsKey = ["study", "sessions", task.id] as const;
  const pomodoroKey = ["study", "pomodoro", plan.id] as const;

  const sessionsQuery = useQuery({
    queryKey: sessionsKey,
    queryFn: () => listStudySessions(plan.id, task.id),
    refetchInterval: 5000,
  });
  const pomodoroQuery = useQuery({
    queryKey: pomodoroKey,
    queryFn: () => getStudyPomodoroState(plan.id),
    refetchInterval: 5000,
  });

  const sessions = sessionsQuery.data?.sessions ?? [];
  const pomodoro = pomodoroQuery.data?.pomodoro;
  const latest = useMemo(
    () =>
      [...sessions].sort((a, b) =>
        b.created_at.localeCompare(a.created_at),
      )[0],
    [sessions],
  );

  const activeSession =
    latest &&
    ["planned", "running", "paused"].includes(latest.status)
      ? latest
      : undefined;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: sessionsKey });
    qc.invalidateQueries({ queryKey: pomodoroKey });
  };

  const create = useMutation({
    mutationFn: () =>
      createStudySession(plan.id, task.id, {
        session_type: pomodoro?.next_session_type,
      }),
    onSuccess: refresh,
  });
  const start = useMutation({
    mutationFn: (sessionId: string) => startStudySession(sessionId),
    onSuccess: refresh,
  });
  const pause = useMutation({
    mutationFn: (sessionId: string) => pauseStudySession(sessionId),
    onSuccess: refresh,
  });
  const resume = useMutation({
    mutationFn: (sessionId: string) => resumeStudySession(sessionId),
    onSuccess: refresh,
  });
  const complete = useMutation({
    mutationFn: (sessionId: string) => completeStudySession(sessionId),
    onSuccess: refresh,
  });
  const abandon = useMutation({
    mutationFn: (sessionId: string) => abandonStudySession(sessionId),
    onSuccess: refresh,
  });

  const busy =
    create.isPending ||
    start.isPending ||
    pause.isPending ||
    resume.isPending ||
    complete.isPending ||
    abandon.isPending;

  const error =
    create.error ||
    start.error ||
    pause.error ||
    resume.error ||
    complete.error ||
    abandon.error;

  const blockedByOtherSession =
    Boolean(pomodoro?.current_session_id) &&
    pomodoro?.current_session_id !== activeSession?.id;

  const nextIsFocus = !pomodoro || pomodoro.next_session_type === "focus";
  const cannotCreateFocus = taskCompleted && nextIsFocus;

  return (
    <div className="mt-5 border-t border-[var(--border)] pt-5">
      <div className="grid gap-5 sm:grid-cols-[170px_minmax(0,1fr)] sm:items-center">
        <PomodoroClock
          session={activeSession}
          defaultMinutes={pomodoro?.next_minutes ?? plan.focus_minutes}
          nextType={pomodoro?.next_session_type ?? "focus"}
        />

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs font-medium uppercase tracking-[0.15em] text-[var(--foreground-muted)]">
              Classic Pomodoro
            </p>
            {pomodoro ? (
              <span className="rounded-full bg-[var(--surface)] px-2 py-1 text-xs text-[var(--foreground-muted)]">
                {pomodoro.focuses_in_cycle}/{pomodoro.cycle_length} 个番茄
              </span>
            ) : null}
          </div>

          <p className="mt-2 text-sm text-[var(--foreground-muted)]">
            {pomodoroHint(activeSession, pomodoro)}
          </p>

          <div className="mt-4 flex flex-wrap gap-2">
            {!activeSession ? (
              <PrimaryButton
                disabled={
                  busy ||
                  !pomodoro ||
                  blockedByOtherSession ||
                  cannotCreateFocus
                }
                onClick={() => create.mutate()}
              >
                {nextActionLabel(pomodoro)}
              </PrimaryButton>
            ) : activeSession.status === "planned" ? (
              <>
                <PrimaryButton
                  disabled={busy}
                  onClick={() => start.mutate(activeSession.id)}
                >
                  {activeSession.session_type === "focus"
                    ? "开始专注"
                    : "开始休息"}
                </PrimaryButton>
                <GhostButton
                  disabled={busy}
                  onClick={() => abandon.mutate(activeSession.id)}
                >
                  取消
                </GhostButton>
              </>
            ) : activeSession.status === "running" ? (
              <>
                <PrimaryButton
                  disabled={busy}
                  onClick={() => pause.mutate(activeSession.id)}
                >
                  暂停
                </PrimaryButton>
                <GhostButton
                  disabled={busy}
                  onClick={() => complete.mutate(activeSession.id)}
                >
                  提前完成
                </GhostButton>
                <GhostButton
                  danger
                  disabled={busy}
                  onClick={() => abandon.mutate(activeSession.id)}
                >
                  放弃
                </GhostButton>
              </>
            ) : (
              <>
                <PrimaryButton
                  disabled={busy}
                  onClick={() => resume.mutate(activeSession.id)}
                >
                  继续
                </PrimaryButton>
                <GhostButton
                  disabled={busy}
                  onClick={() => complete.mutate(activeSession.id)}
                >
                  完成
                </GhostButton>
                <GhostButton
                  danger
                  disabled={busy}
                  onClick={() => abandon.mutate(activeSession.id)}
                >
                  放弃
                </GhostButton>
              </>
            )}
          </div>

          {blockedByOtherSession ? (
            <p className="mt-3 text-xs text-[var(--foreground-muted)]">
              当前计划已有另一个番茄会话，先完成或结束它。
            </p>
          ) : null}

          {cannotCreateFocus ? (
            <p className="mt-3 text-xs text-[var(--foreground-muted)]">
              这个任务已完成；下一轮专注请选择尚未完成的任务。
            </p>
          ) : null}

          {error ? (
            <p className="mt-3 text-sm text-red-500">{messageOf(error)}</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function PomodoroClock({
  session,
  defaultMinutes,
  nextType,
}: {
  session?: StudySession;
  defaultMinutes: number;
  nextType: StudySession["session_type"];
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const { remainingSeconds, totalSeconds } = useMemo(() => {
    const total = Math.max(1, (session?.planned_minutes ?? defaultMinutes) * 60);

    if (!session) {
      return { remainingSeconds: total, totalSeconds: total };
    }

    if (session.status === "running" && session.expected_end_at) {
      return {
        remainingSeconds: Math.max(
          0,
          Math.ceil(
            (new Date(session.expected_end_at).getTime() - now) / 1000,
          ),
        ),
        totalSeconds: total,
      };
    }

    if (session.status === "completed") {
      return { remainingSeconds: 0, totalSeconds: total };
    }

    return {
      remainingSeconds: Math.max(
        0,
        total - session.actual_minutes * 60,
      ),
      totalSeconds: total,
    };
  }, [session, defaultMinutes, now]);

  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;
  const elapsed = Math.min(totalSeconds, Math.max(0, totalSeconds - remainingSeconds));
  const progress = Math.round((elapsed / totalSeconds) * 100);

  return (
    <div className="flex justify-center sm:justify-start">
      <div
        className="relative flex h-40 w-40 shrink-0 items-center justify-center rounded-full"
        style={{
          background: `conic-gradient(var(--accent) ${progress}%, var(--border) ${progress}% 100%)`,
        }}
      >
        <div className="absolute inset-[7px] rounded-full bg-[var(--surface-raised)]" />
        <div className="relative z-10 text-center">
          <p className="font-mono text-3xl font-semibold tabular-nums tracking-tight">
            {String(minutes).padStart(2, "0")}:
            {String(seconds).padStart(2, "0")}
          </p>
          <p className="mt-1 text-xs text-[var(--foreground-muted)]">
            {session
              ? sessionStatusText(session.status, session.session_type)
              : sessionTypeText(nextType)}
          </p>
        </div>
      </div>
    </div>
  );
}

function EmptyStudy() {
  return (
    <section className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] px-6 py-16 text-center">
      <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-[var(--surface)] text-2xl">
        ◷
      </div>
      <h2 className="mt-4 font-semibold">从一个简单的计划开始</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--foreground-muted)]">
        在左侧创建学习计划，然后添加任务。每个任务都可以直接启动自己的番茄钟。
      </p>
    </section>
  );
}

function StatusPill({ status }: { status: StudyPlan["status"] }) {
  return (
    <span className="inline-flex rounded-full bg-[var(--surface)] px-2.5 py-1 text-xs font-medium text-[var(--foreground-muted)]">
      {planStatusText(status)}
    </span>
  );
}

function PrimaryButton({
  children,
  onClick,
  disabled = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-[var(--radius-md)] bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white disabled:opacity-45"
    >
      {children}
    </button>
  );
}

function SecondaryButton({
  children,
  onClick,
  danger = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-[var(--radius-md)] border px-3 py-2 text-sm ${
        danger
          ? "border-red-400/50 text-red-500"
          : "border-[var(--border-strong)]"
      }`}
    >
      {children}
    </button>
  );
}

function GhostButton({
  children,
  onClick,
  danger = false,
  disabled = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-[var(--radius-md)] px-3 py-2.5 text-sm disabled:opacity-45 ${
        danger ? "text-red-500" : "text-[var(--foreground-muted)]"
      }`}
    >
      {children}
    </button>
  );
}

function planStatusText(status: StudyPlan["status"]) {
  if (status === "active") return "进行中";
  if (status === "paused") return "已暂停";
  if (status === "completed") return "已完成";
  if (status === "archived") return "已归档";
  return "草稿";
}

function taskStatusText(status: StudyTaskStatus) {
  if (status === "in_progress") return "进行中";
  if (status === "completed") return "已完成";
  if (status === "skipped") return "已跳过";
  if (status === "deferred") return "已推迟";
  return "未开始";
}

function sessionTypeText(type: StudySession["session_type"]) {
  if (type === "short_break") return "短休息";
  if (type === "long_break") return "长休息";
  if (type === "review") return "复习";
  if (type === "quiz") return "测验";
  if (type === "flashcard") return "闪卡";
  return "专注";
}

function sessionStatusText(
  status: StudySession["status"],
  type: StudySession["session_type"],
) {
  const noun = sessionTypeText(type);
  if (status === "running") return type === "focus" ? "专注中" : `${noun}中`;
  if (status === "paused") return "已暂停";
  if (status === "completed") return "已完成";
  if (status === "abandoned") return "已放弃";
  return `等待${noun}`;
}

function nextActionLabel(state?: StudyPomodoroState) {
  if (!state) return "准备番茄钟";
  if (state.next_session_type === "short_break") {
    return `开始 ${state.next_minutes} 分钟短休息`;
  }
  if (state.next_session_type === "long_break") {
    return `开始 ${state.next_minutes} 分钟长休息`;
  }
  return `新建 ${state.next_minutes} 分钟专注`;
}

function pomodoroHint(
  session?: StudySession,
  state?: StudyPomodoroState,
) {
  if (session?.status === "planned") {
    return session.session_type === "focus"
      ? "专注计时已准备好。"
      : "休息计时已准备好。";
  }
  if (session?.status === "running") {
    return session.session_type === "focus"
      ? "保持当前节奏，时间由服务器记录。"
      : "离开任务一会儿，让注意力恢复。";
  }
  if (session?.status === "paused") {
    return "暂停期间不会消耗剩余时间。";
  }

  if (!state) return "经典节奏：25 分钟专注，5 分钟短休息。";
  if (state.next_session_type === "long_break") {
    return `已完成 ${state.focuses_in_cycle}/${state.cycle_length} 个番茄，下一步是长休息。`;
  }
  if (state.next_session_type === "short_break") {
    return `完成一个番茄后，先进行 ${state.next_minutes} 分钟短休息。`;
  }
  return `下一轮为 ${state.next_minutes} 分钟专注；第 ${state.cycle_length} 个番茄后进入长休息。`;
}

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <section className="mx-auto w-full max-w-6xl px-5 py-7 sm:px-8 sm:py-9">
      {children}
    </section>
  );
}
