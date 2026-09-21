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
  listStudyPlans,
  listStudySessions,
  pauseStudySession,
  resumeStudySession,
  setStudyTaskStatus,
  startStudySession,
  updateStudyPlan,
  type StudyPlan,
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
    if (!selectedPlanId || !plans.some((p) => p.id === selectedPlanId)) {
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
      const end = endDate.toISOString().slice(0, 10);
      return createStudyPlan({
        title,
        start_date: start,
        end_date: end,
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
        title="学习计划"
        description="Canonical Study Core · Pomodoro 由服务器计时，页面倒计时仅用于显示。"
      />

      <section className="mt-5 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-5">
        <div className="flex flex-wrap gap-2">
          <input
            value={newPlanTitle}
            onChange={(event) => setNewPlanTitle(event.target.value)}
            placeholder="新学习计划名称"
            className="min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
          />
          <button
            onClick={() => createPlan.mutate()}
            disabled={createPlan.isPending}
            className="rounded-[var(--radius-md)] bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            新建计划
          </button>
        </div>
        {createPlan.error && (
          <p className="mt-2 text-sm text-red-500">{messageOf(createPlan.error)}</p>
        )}
      </section>

      {plans.length > 0 && (
        <div className="mt-5 flex gap-2 overflow-x-auto pb-2">
          {plans.map((plan) => (
            <button
              key={plan.id}
              onClick={() => setSelectedPlanId(plan.id)}
              className={`min-w-44 rounded-[var(--radius-md)] border px-3 py-2 text-left ${
                plan.id === selectedPlan?.id
                  ? "border-[var(--accent)] bg-[var(--surface-raised)]"
                  : "border-[var(--border)] bg-[var(--surface)]"
              }`}
            >
              <b className="block truncate text-sm">{plan.title}</b>
              <span className="mt-1 block text-xs text-[var(--foreground-muted)]">
                {plan.status} · {plan.tasks.length} 个任务
              </span>
            </button>
          ))}
        </div>
      )}

      {!selectedPlan ? (
        <section className="mt-6 rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] p-8 text-center">
          <p className="font-medium">还没有学习计划</p>
          <p className="mt-2 text-sm text-[var(--foreground-muted)]">
            创建第一个计划后，可以添加任务并启动 Pomodoro。
          </p>
        </section>
      ) : (
        <PlanPanel
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
    </Frame>
  );
}

function PlanPanel({
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
  return (
    <>
      <section className="mt-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-[var(--foreground-muted)]">
              {plan.start_date} → {plan.end_date}
            </p>
            <h2 className="mt-1 text-xl font-semibold">{plan.title}</h2>
            <p className="mt-2 text-sm text-[var(--foreground-muted)]">
              专注 {plan.focus_minutes} 分钟 · 休息 {plan.break_minutes} 分钟 ·
              长休息 {plan.long_break_minutes} 分钟
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {plan.status !== "active" && (
              <SmallButton onClick={() => onPlanStatus("active")}>
                启用计划
              </SmallButton>
            )}
            {plan.status === "active" && (
              <SmallButton onClick={() => onPlanStatus("paused")}>
                暂停计划
              </SmallButton>
            )}
            <SmallButton danger onClick={onDeletePlan}>
              删除计划
            </SmallButton>
          </div>
        </div>
      </section>

      <section className="mt-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-5">
        <h2 className="font-semibold">添加学习任务</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <input
            value={newTaskTitle}
            onChange={(event) => onNewTaskTitle(event.target.value)}
            placeholder="例如：复习免疫系统第三章"
            className="min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
          />
          <button
            onClick={onCreateTask}
            disabled={creatingTask}
            className="rounded-[var(--radius-md)] bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            添加任务
          </button>
        </div>
        {taskError ? (
          <p className="mt-2 text-sm text-red-500">{messageOf(taskError)}</p>
        ) : null}
      </section>

      <div className="mt-4 space-y-4">
        {plan.tasks.length === 0 ? (
          <section className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] p-6 text-center text-sm text-[var(--foreground-muted)]">
            当前计划还没有任务。
          </section>
        ) : (
          plan.tasks.map((task) => (
            <TaskCard
              key={task.id}
              plan={plan}
              task={task}
              onStatus={(status) => onTaskStatus(task.id, status)}
              onDelete={() => onDeleteTask(task.id)}
            />
          ))
        )}
      </div>
    </>
  );
}

function TaskCard({
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
  return (
    <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{task.title}</h3>
          {task.description && (
            <p className="mt-1 text-sm text-[var(--foreground-muted)]">
              {task.description}
            </p>
          )}
          <p className="mt-2 text-xs text-[var(--foreground-muted)]">
            {task.scheduled_date} · 计划 {task.planned_minutes} 分钟 · {task.status}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {task.status === "planned" && (
            <SmallButton onClick={() => onStatus("in_progress")}>
              标记进行中
            </SmallButton>
          )}
          {task.status !== "completed" && (
            <SmallButton onClick={() => onStatus("completed")}>
              完成任务
            </SmallButton>
          )}
          <SmallButton danger onClick={onDelete}>
            删除
          </SmallButton>
        </div>
      </div>
      <PomodoroCard plan={plan} task={task} />
    </section>
  );
}

function PomodoroCard({
  plan,
  task,
}: {
  plan: StudyPlan;
  task: StudyTask;
}) {
  const qc = useQueryClient();
  const sessionsKey = ["study", "sessions", task.id] as const;

  const sessionsQuery = useQuery({
    queryKey: sessionsKey,
    queryFn: () => listStudySessions(plan.id, task.id),
    refetchInterval: 5000,
  });

  const sessions = sessionsQuery.data?.sessions ?? [];
  const latest = useMemo(
    () => [...sessions].sort((a, b) => b.created_at.localeCompare(a.created_at))[0],
    [sessions],
  );

  const refresh = () =>
    qc.invalidateQueries({
      queryKey: sessionsKey,
    });

  const create = useMutation({
    mutationFn: () =>
      createStudySession(plan.id, task.id, {
        planned_minutes: plan.focus_minutes,
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

  return (
    <div className="mt-4 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs text-[var(--foreground-muted)]">
            Pomodoro · 服务器时间为准
          </p>
          <PomodoroClock session={latest} defaultMinutes={plan.focus_minutes} />
        </div>
        <div className="flex flex-wrap gap-2">
          {!latest || ["completed", "abandoned"].includes(latest.status) ? (
            <SmallButton disabled={busy} onClick={() => create.mutate()}>
              新建专注
            </SmallButton>
          ) : latest.status === "planned" ? (
            <>
              <SmallButton disabled={busy} onClick={() => start.mutate(latest.id)}>
                开始
              </SmallButton>
              <SmallButton
                danger
                disabled={busy}
                onClick={() => abandon.mutate(latest.id)}
              >
                放弃
              </SmallButton>
            </>
          ) : latest.status === "running" ? (
            <>
              <SmallButton disabled={busy} onClick={() => pause.mutate(latest.id)}>
                暂停
              </SmallButton>
              <SmallButton
                disabled={busy}
                onClick={() => complete.mutate(latest.id)}
              >
                提前完成
              </SmallButton>
              <SmallButton
                danger
                disabled={busy}
                onClick={() => abandon.mutate(latest.id)}
              >
                放弃
              </SmallButton>
            </>
          ) : (
            <>
              <SmallButton disabled={busy} onClick={() => resume.mutate(latest.id)}>
                继续
              </SmallButton>
              <SmallButton
                disabled={busy}
                onClick={() => complete.mutate(latest.id)}
              >
                完成
              </SmallButton>
              <SmallButton
                danger
                disabled={busy}
                onClick={() => abandon.mutate(latest.id)}
              >
                放弃
              </SmallButton>
            </>
          )}
        </div>
      </div>

      {error ? (
        <p className="mt-2 text-sm text-red-500">{messageOf(error)}</p>
      ) : null}
    </div>
  );
}

function PomodoroClock({
  session,
  defaultMinutes,
}: {
  session?: StudySession;
  defaultMinutes: number;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const remainingSeconds = useMemo(() => {
    if (!session) return defaultMinutes * 60;
    if (session.status === "running" && session.expected_end_at) {
      return Math.max(
        0,
        Math.ceil((new Date(session.expected_end_at).getTime() - now) / 1000),
      );
    }
    if (session.status === "completed") return 0;
    return Math.max(
      0,
      session.planned_minutes * 60 - session.actual_minutes * 60,
    );
  }, [session, defaultMinutes, now]);

  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;

  return (
    <>
      <p className="mt-1 font-mono text-3xl font-semibold tabular-nums">
        {String(minutes).padStart(2, "0")}:{String(seconds).padStart(2, "0")}
      </p>
      <p className="mt-1 text-xs text-[var(--foreground-muted)]">
        {session ? statusText(session.status) : "尚未建立专注会话"}
      </p>
    </>
  );
}

function statusText(status: StudySession["status"]) {
  if (status === "planned") return "等待开始";
  if (status === "running") return "专注中";
  if (status === "paused") return "已暂停";
  if (status === "completed") return "已完成";
  return "已放弃";
}

function SmallButton({
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
      onClick={onClick}
      disabled={disabled}
      className={`rounded-[var(--radius-md)] border px-3 py-2 text-sm disabled:opacity-45 ${
        danger
          ? "border-red-400/50 text-red-500"
          : "border-[var(--border-strong)]"
      }`}
    >
      {children}
    </button>
  );
}

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <section className="mx-auto w-full max-w-5xl px-5 py-7 sm:px-9 sm:py-10">
      {children}
    </section>
  );
}
