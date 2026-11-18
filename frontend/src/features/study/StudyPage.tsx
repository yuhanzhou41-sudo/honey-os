import { fetchCompanionBootstrap } from "../../api/companion";
import { listStudyReminders, planExportUrl, planTemplateUrl, setStudyReminder } from "../../api/study-planning";
import StudyReviewPanel, { StudyQuestionDialog } from "./StudyReviewPanel";
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
  importStudyPlanMarkdown,
  listStudyPlans,
  listStudySessions,
  pauseStudySession,
  previewStudyPlanMarkdown,
  resumeStudySession,
  setStudyTaskStatus,
  startStudySession,
  updateStudyPlan,
  updateStudyTask,
  type StudyPlan,
  type StudyPomodoroState,
  type StudySession,
  type StudyTask,
  type StudyTaskStatus,
} from "../../api/study";
import { PageHeader } from "../../components/honey/PageHeader";
import { ErrorState, LoadingState } from "../../components/honey/PageState";
import { StudyLibraryPanel } from "./StudyLibraryPanel";
import { StudyTextbookPanel } from "./StudyTextbookPanel";

const plansKey = ["study", "plans"] as const;

type PlanDraft = {
  title: string;
  description: string;
  start_date: string;
  end_date: string;
  goalsText: string;
  focus_minutes: string;
  break_minutes: string;
  long_break_minutes: string;
  long_break_after_sessions: string;
  status: StudyPlan["status"];
};

type TaskDraft = {
  title: string;
  description: string;
  scheduled_date: string;
  planned_minutes: string;
  review_required: boolean;
  status: StudyTaskStatus;
};

type DrawerKind = "library" | "review" | "qa" | "textbook" | null;

function planDraftOf(plan: StudyPlan): PlanDraft {
  return {
    title: plan.title,
    description: plan.description,
    start_date: plan.start_date,
    end_date: plan.end_date,
    goalsText: plan.goals.join("\n"),
    focus_minutes: String(plan.focus_minutes),
    break_minutes: String(plan.break_minutes),
    long_break_minutes: String(plan.long_break_minutes),
    long_break_after_sessions: String(plan.long_break_after_sessions),
    status: plan.status,
  };
}

function taskDraftOf(task: StudyTask): TaskDraft {
  return {
    title: task.title,
    description: task.description,
    scheduled_date: task.scheduled_date,
    planned_minutes: String(task.planned_minutes),
    review_required: task.review_required,
    status: task.status,
  };
}

function positiveInt(value: string, field: string) {
  const n = Number(value);
  if (!Number.isInteger(n) || n <= 0) throw new Error(`${field} 必须是正整数`);
  return n;
}

function localDate() {
  return new Date().toLocaleDateString("en-CA");
}

function dateRange(start: string, end: string) {
  const out: string[] = [];
  const cursor = new Date(`${start}T00:00:00`);
  const last = new Date(`${end}T00:00:00`);
  while (cursor <= last && out.length < 370) {
    out.push(cursor.toLocaleDateString("en-CA"));
    cursor.setDate(cursor.getDate() + 1);
  }
  return out.length ? out : [start];
}

function chooseInitialDate(plan?: StudyPlan) {
  if (!plan) return "";
  const today = localDate();
  if (today >= plan.start_date && today <= plan.end_date) return today;
  return plan.tasks[0]?.scheduled_date || plan.start_date;
}

export function StudyPage() {
  const qc = useQueryClient();
  const plansQuery = useQuery({ queryKey: plansKey, queryFn: listStudyPlans });
  const plans = plansQuery.data?.plans ?? [];

  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [newPlanTitle, setNewPlanTitle] = useState("");
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [planEditing, setPlanEditing] = useState(false);
  const [planDraft, setPlanDraft] = useState<PlanDraft | null>(null);
  const [taskEditingId, setTaskEditingId] = useState("");
  const [taskDraft, setTaskDraft] = useState<TaskDraft | null>(null);
  const [drawer, setDrawer] = useState<DrawerKind>(null);
  const [importPreview, setImportPreview] = useState<StudyPlan | null>(null);
  const [importMarkdown, setImportMarkdown] = useState("");
  const [importFileName, setImportFileName] = useState("");
  const [pomodoroTaskId, setPomodoroTaskId] = useState("");
  const [pomodoroOpen, setPomodoroOpen] = useState(false);

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

  useEffect(() => {
    setPlanEditing(false);
    setPlanDraft(selectedPlan ? planDraftOf(selectedPlan) : null);
    setTaskEditingId("");
    setTaskDraft(null);
    setSelectedDate(chooseInitialDate(selectedPlan));
    setPomodoroTaskId("");
  }, [selectedPlan?.id]);

  const dayTasks = useMemo(
    () =>
      selectedPlan?.tasks
        .filter((task) => task.scheduled_date === selectedDate)
        .sort((a, b) => a.order_index - b.order_index) ?? [],
    [selectedPlan, selectedDate],
  );

  useEffect(() => {
    if (!selectedPlan) return;
    if (
      pomodoroTaskId &&
      selectedPlan.tasks.some((task) => task.id === pomodoroTaskId)
    ) {
      return;
    }
    const candidate =
      dayTasks.find((task) => task.status !== "completed") ??
      selectedPlan.tasks.find((task) => task.status !== "completed") ??
      dayTasks[0] ??
      selectedPlan.tasks[0];
    setPomodoroTaskId(candidate?.id ?? "");
  }, [selectedPlan, dayTasks, pomodoroTaskId]);

  const pomodoroTask =
    selectedPlan?.tasks.find((task) => task.id === pomodoroTaskId);

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
        scheduled_date: selectedDate || selectedPlan.start_date,
        planned_minutes: selectedPlan.focus_minutes,
      });
    },
    onSuccess: () => {
      setNewTaskTitle("");
      refreshPlans();
    },
  });

  const savePlanMutation = useMutation({
    mutationFn: async () => {
      if (!selectedPlan || !planDraft) throw new Error("请先选择学习计划");
      const title = planDraft.title.trim();
      if (!title) throw new Error("计划名称不能为空");
      return updateStudyPlan(selectedPlan.id, {
        title,
        description: planDraft.description.trim(),
        start_date: planDraft.start_date,
        end_date: planDraft.end_date,
        goals: planDraft.goalsText
          .split(/\r?\n/)
          .map((x) => x.trim())
          .filter(Boolean),
        focus_minutes: positiveInt(planDraft.focus_minutes, "专注时长"),
        break_minutes: positiveInt(planDraft.break_minutes, "短休息时长"),
        long_break_minutes: positiveInt(
          planDraft.long_break_minutes,
          "长休息时长",
        ),
        long_break_after_sessions: positiveInt(
          planDraft.long_break_after_sessions,
          "长休息轮数",
        ),
        status: planDraft.status,
      });
    },
    onSuccess: ({ plan }) => {
      setPlanDraft(planDraftOf(plan));
      setPlanEditing(false);
      refreshPlans();
    },
  });

  const saveTaskMutation = useMutation({
    mutationFn: async () => {
      if (!selectedPlan || !taskEditingId || !taskDraft) {
        throw new Error("没有正在编辑的任务");
      }
      const title = taskDraft.title.trim();
      if (!title) throw new Error("任务名称不能为空");
      return updateStudyTask(selectedPlan.id, taskEditingId, {
        title,
        description: taskDraft.description.trim(),
        scheduled_date: taskDraft.scheduled_date,
        planned_minutes: positiveInt(taskDraft.planned_minutes, "任务时长"),
        review_required: taskDraft.review_required,
        status: taskDraft.status,
      });
    },
    onSuccess: () => {
      setTaskEditingId("");
      setTaskDraft(null);
      refreshPlans();
    },
  });

  const deletePlanMutation = useMutation({
    mutationFn: (id: string) => deleteStudyPlan(id),
    onSuccess: () => { setSelectedPlanId(""); refreshPlans(); },
  });

  const setPlanStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: StudyPlan["status"] }) =>
      updateStudyPlan(id, { status }),
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

  const previewImport = useMutation({
    mutationFn: (markdown: string) => previewStudyPlanMarkdown(markdown),
    onSuccess: ({ plan }) => setImportPreview(plan),
  });

  const confirmImport = useMutation({
    mutationFn: () => importStudyPlanMarkdown(importMarkdown),
    onSuccess: ({ plan }) => {
      setImportPreview(null);
      setImportMarkdown("");
      setImportFileName("");
      setSelectedPlanId(plan.id);
      refreshPlans();
    },
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
        description="今天只看今天要完成的内容；资料、教材、复习、答疑和番茄钟需要时再展开。"
      />

      <GrowthStrip />

      <details className="mt-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)]">
        <summary className="cursor-pointer list-none px-4 py-3 text-sm font-medium">
          计划管理
          <span className="ml-2 text-xs font-normal text-[var(--foreground-muted)]">
            切换 / 新建 / 导入
          </span>
        </summary>
        <div className="grid gap-4 border-t border-[var(--border)] p-4 lg:grid-cols-2">
          <div>
            <label className="text-xs text-[var(--foreground-muted)]">
              当前计划
            </label>
            <select
              value={selectedPlan?.id ?? ""}
              onChange={(event) => setSelectedPlanId(event.target.value)}
              className="mt-1 w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
            >
              {plans.map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.title}
                </option>
              ))}
            </select>
            <div className="mt-3 flex gap-2">
              <input
                value={newPlanTitle}
                onChange={(event) => setNewPlanTitle(event.target.value)}
                placeholder="新计划名称"
                className="min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
              />
              <SecondaryButton onClick={() => createPlan.mutate()}>
                ＋ 新建
              </SecondaryButton>
              {selectedPlan && <SecondaryButton danger disabled={deletePlanMutation.isPending} onClick={() => {
                if (window.confirm("删除整个计划「" + selectedPlan.title + "」以及其中的任务和提醒？")) {
                  deletePlanMutation.mutate(selectedPlan.id);
                }
              }}>删除整个计划</SecondaryButton>}
            </div>
            {selectedPlan && <a className="mt-2 block text-sm underline" download href={planExportUrl(selectedPlan.id)}>下载当前计划 Markdown</a>}
            {deletePlanMutation.error && <p role="alert" className="mt-2 text-sm text-red-600">{messageOf(deletePlanMutation.error)}</p>}
            {createPlan.error ? (
              <p className="mt-2 text-xs text-red-500">
                {messageOf(createPlan.error)}
              </p>
            ) : null}
          </div>

          <div>
            <p className="text-xs text-[var(--foreground-muted)]">
              导入 StudyPlan Markdown
              {" · "}<a className="underline" href={planTemplateUrl()} download>下载计划模板</a>
            </p>
            <label className="mt-1 flex cursor-pointer items-center justify-between gap-3 rounded-[var(--radius-md)] border border-dashed border-[var(--border-strong)] bg-[var(--surface)] px-3 py-3 text-sm">
              <span className="truncate">
                {importFileName || "选择 .md 文件进行预览"}
              </span>
              <span className="shrink-0 text-[var(--foreground-muted)]">
                选择文件
              </span>
              <input
                type="file"
                accept=".md,text/markdown,text/plain"
                className="hidden"
                onChange={async (event) => {
                  const file = event.target.files?.[0];
                  if (!file) return;
                  const text = await file.text();
                  setImportFileName(file.name);
                  setImportMarkdown(text);
                  previewImport.mutate(text);
                  event.currentTarget.value = "";
                }}
              />
            </label>
            <p className="mt-2 text-xs leading-5 text-[var(--foreground-muted)]">
              先预览，不写数据库；确认导入后才进入 canonical StudyPlan。
            </p>
            {previewImport.error ? (
              <p className="mt-2 text-xs text-red-500">
                {messageOf(previewImport.error)}
              </p>
            ) : null}
          </div>
        </div>
      </details>

      <main className="mt-5 min-w-0">
        {!selectedPlan ? (
          <EmptyStudy />
        ) : (
          <PlanWorkspace
            plan={selectedPlan}
            selectedDate={selectedDate}
            onSelectedDate={setSelectedDate}
            newTaskTitle={newTaskTitle}
            onNewTaskTitle={setNewTaskTitle}
            onCreateTask={() => createTask.mutate()}
            creatingTask={createTask.isPending}
            taskError={createTask.error}
            planEditing={planEditing}
            planDraft={planDraft}
            onPlanDraft={setPlanDraft}
            onStartPlanEdit={() => {
              setPlanDraft(planDraftOf(selectedPlan));
              setPlanEditing(true);
            }}
            onCancelPlanEdit={() => {
              setPlanDraft(planDraftOf(selectedPlan));
              setPlanEditing(false);
            }}
            onSavePlan={() => savePlanMutation.mutate()}
            savingPlan={savePlanMutation.isPending}
            planSaveError={savePlanMutation.error}
            taskEditingId={taskEditingId}
            taskDraft={taskDraft}
            onStartTaskEdit={(task) => {
              setTaskEditingId(task.id);
              setTaskDraft(taskDraftOf(task));
            }}
            onTaskDraft={setTaskDraft}
            onCancelTaskEdit={() => {
              setTaskEditingId("");
              setTaskDraft(null);
            }}
            onSaveTask={() => saveTaskMutation.mutate()}
            savingTask={saveTaskMutation.isPending}
            taskSaveError={saveTaskMutation.error}
            onPlanStatus={(status) =>
              setPlanStatus.mutate({ id: selectedPlan.id, status })
            }
            onDeletePlan={() => {
              if (!deletePlanMutation.isPending &&
                  window.confirm("删除整个计划「" + selectedPlan.title + "」以及其中的任务和提醒？")) {
                deletePlanMutation.mutate(selectedPlan.id);
              }
            }}
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
            onFocusTask={(task) => {
              setPomodoroTaskId(task.id);
              setPomodoroOpen(true);
            }}
          />
        )}
      </main>

      <ToolRail drawer={drawer} onDrawer={setDrawer} />

      {drawer ? (
        <UtilityDrawer kind={drawer} onClose={() => setDrawer(null)} planId={selectedPlan?.id}
          todayTasks={selectedPlan?.tasks.filter(task => task.scheduled_date === localDate()) ?? []} />
      ) : null}

      {selectedPlan ? (
        <FloatingPomodoro
          plan={selectedPlan}
          task={pomodoroTask}
          open={pomodoroOpen}
          onOpen={setPomodoroOpen}
        />
      ) : null}

      {importPreview ? (
        <ImportPreviewDialog
          plan={importPreview}
          fileName={importFileName}
          busy={confirmImport.isPending}
          error={confirmImport.error}
          onCancel={() => setImportPreview(null)}
          onConfirm={() => confirmImport.mutate()}
        />
      ) : null}
    </Frame>
  );
}

function GrowthStrip() {
  return (
    <section className="mt-5 grid gap-3 sm:grid-cols-3">
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] px-4 py-3">
        <p className="text-xs text-[var(--foreground-muted)]">阳光点</p>
        <p className="mt-1 text-lg font-semibold">☀️ —</p>
        <p className="mt-1 text-xs text-[var(--foreground-muted)]">
          奖励系统预留
        </p>
      </div>
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] px-4 py-3">
        <p className="text-xs text-[var(--foreground-muted)]">小花盆</p>
        <p className="mt-1 text-lg font-semibold">🫘 待成长</p>
        <p className="mt-1 text-xs text-[var(--foreground-muted)]">
          成长逻辑后续接入
        </p>
      </div>
      <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] px-4 py-3">
        <p className="text-xs text-[var(--foreground-muted)]">每日复盘</p>
        <p className="mt-1 text-lg font-semibold">HoneyOS · 预留</p>
        <p className="mt-1 text-xs text-[var(--foreground-muted)]">
          每日学习监督后续接入
        </p>
      </div>
    </section>
  );
}

function PlanWorkspace({
  plan,
  selectedDate,
  onSelectedDate,
  newTaskTitle,
  onNewTaskTitle,
  onCreateTask,
  creatingTask,
  taskError,
  planEditing,
  planDraft,
  onPlanDraft,
  onStartPlanEdit,
  onCancelPlanEdit,
  onSavePlan,
  savingPlan,
  planSaveError,
  taskEditingId,
  taskDraft,
  onStartTaskEdit,
  onTaskDraft,
  onCancelTaskEdit,
  onSaveTask,
  savingTask,
  taskSaveError,
  onPlanStatus,
  onDeletePlan,
  onTaskStatus,
  onDeleteTask,
  onFocusTask,
}: {
  plan: StudyPlan;
  selectedDate: string;
  onSelectedDate: (date: string) => void;
  newTaskTitle: string;
  onNewTaskTitle: (value: string) => void;
  onCreateTask: () => void;
  creatingTask: boolean;
  taskError: unknown;
  planEditing: boolean;
  planDraft: PlanDraft | null;
  onPlanDraft: (draft: PlanDraft | null) => void;
  onStartPlanEdit: () => void;
  onCancelPlanEdit: () => void;
  onSavePlan: () => void;
  savingPlan: boolean;
  planSaveError: unknown;
  taskEditingId: string;
  taskDraft: TaskDraft | null;
  onStartTaskEdit: (task: StudyTask) => void;
  onTaskDraft: (draft: TaskDraft | null) => void;
  onCancelTaskEdit: () => void;
  onSaveTask: () => void;
  savingTask: boolean;
  taskSaveError: unknown;
  onPlanStatus: (status: StudyPlan["status"]) => void;
  onDeletePlan: () => void;
  onTaskStatus: (taskId: string, status: StudyTaskStatus) => void;
  onDeleteTask: (taskId: string) => void;
  onFocusTask: (task: StudyTask) => void;
}) {
  const completed = plan.tasks.filter(
    (task) => task.status === "completed",
  ).length;
  const total = plan.tasks.length;
  const progress = total ? Math.round((completed / total) * 100) : 0;
  const dates = useMemo(
    () => dateRange(plan.start_date, plan.end_date),
    [plan.start_date, plan.end_date],
  );
  const tasks = useMemo(
    () =>
      plan.tasks
        .filter((task) => task.scheduled_date === selectedDate)
        .sort((a, b) => a.order_index - b.order_index),
    [plan.tasks, selectedDate],
  );
  const dayIndex = Math.max(0, dates.indexOf(selectedDate));
  const dayCompleted = tasks.filter(
    (task) => task.status === "completed",
  ).length;

  return (
    <div className="space-y-5">
      <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill status={plan.status} />
              <span className="text-xs text-[var(--foreground-muted)]">
                {plan.start_date} → {plan.end_date}
              </span>
              <span className="text-xs text-[var(--foreground-muted)]">
                来源：{plan.source_type}
              </span>
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight">
              {plan.title}
            </h2>
            {plan.description ? (
              <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--foreground-muted)]">
                {plan.description}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <SecondaryButton onClick={onStartPlanEdit}>
              编辑计划
            </SecondaryButton>
            {plan.status !== "active" ? (
              <SecondaryButton onClick={() => onPlanStatus("active")}>
                启用
              </SecondaryButton>
            ) : (
              <SecondaryButton onClick={() => onPlanStatus("paused")}>
                暂停
              </SecondaryButton>
            )}
            <SecondaryButton danger onClick={onDeletePlan}>
              删除整个计划
            </SecondaryButton>
          </div>
        </div>

        {planEditing && planDraft ? (
          <div className="mt-4 grid gap-3 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4">
            <input
              value={planDraft.title}
              onChange={(e) =>
                onPlanDraft({ ...planDraft, title: e.target.value })
              }
              className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
            />
            <textarea
              value={planDraft.description}
              onChange={(e) =>
                onPlanDraft({ ...planDraft, description: e.target.value })
              }
              rows={3}
              placeholder="计划说明"
              className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
            />
            <div className="grid gap-3 sm:grid-cols-2">
              <input
                type="date"
                value={planDraft.start_date}
                onChange={(e) =>
                  onPlanDraft({ ...planDraft, start_date: e.target.value })
                }
                className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
              />
              <input
                type="date"
                value={planDraft.end_date}
                onChange={(e) =>
                  onPlanDraft({ ...planDraft, end_date: e.target.value })
                }
                className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
              />
            </div>
            <textarea
              value={planDraft.goalsText}
              onChange={(e) =>
                onPlanDraft({ ...planDraft, goalsText: e.target.value })
              }
              rows={3}
              placeholder="学习目标，每行一个"
              className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
            />
            <div className="grid gap-3 sm:grid-cols-4">
              <input
                type="number"
                min={1}
                value={planDraft.focus_minutes}
                onChange={(e) =>
                  onPlanDraft({
                    ...planDraft,
                    focus_minutes: e.target.value,
                  })
                }
                placeholder="专注"
                className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
              />
              <input
                type="number"
                min={1}
                value={planDraft.break_minutes}
                onChange={(e) =>
                  onPlanDraft({
                    ...planDraft,
                    break_minutes: e.target.value,
                  })
                }
                placeholder="短休息"
                className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
              />
              <input
                type="number"
                min={1}
                value={planDraft.long_break_minutes}
                onChange={(e) =>
                  onPlanDraft({
                    ...planDraft,
                    long_break_minutes: e.target.value,
                  })
                }
                placeholder="长休息"
                className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
              />
              <input
                type="number"
                min={1}
                value={planDraft.long_break_after_sessions}
                onChange={(e) =>
                  onPlanDraft({
                    ...planDraft,
                    long_break_after_sessions: e.target.value,
                  })
                }
                placeholder="长休息轮数"
                className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
              />
            </div>
            <select
              value={planDraft.status}
              onChange={(e) =>
                onPlanDraft({
                  ...planDraft,
                  status: e.target.value as StudyPlan["status"],
                })
              }
              className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] px-3 py-2 text-sm"
            >
              <option value="draft">草稿</option>
              <option value="active">进行中</option>
              <option value="paused">暂停</option>
              <option value="completed">已完成</option>
              <option value="archived">已归档</option>
            </select>
            <div className="flex gap-2">
              <SecondaryButton onClick={onSavePlan}>
                {savingPlan ? "保存中…" : "保存计划"}
              </SecondaryButton>
              <SecondaryButton onClick={onCancelPlanEdit}>
                取消
              </SecondaryButton>
            </div>
            {planSaveError ? (
              <p className="text-sm text-red-500">
                {messageOf(planSaveError)}
              </p>
            ) : null}
          </div>
        ) : null}

        {plan.goals.length ? (
          <div className="mt-5 flex flex-wrap gap-2">
            {plan.goals.map((goal) => (
              <span
                key={goal}
                className="rounded-full bg-[var(--surface)] px-3 py-1.5 text-xs text-[var(--foreground-muted)]"
              >
                {goal}
              </span>
            ))}
          </div>
        ) : null}

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
          <div className="flex flex-wrap gap-3 text-xs text-[var(--foreground-muted)]">
            <span>专注 {plan.focus_minutes}m</span>
            <span>短休 {plan.break_minutes}m</span>
            <span>
              {plan.long_break_after_sessions} 轮后长休{" "}
              {plan.long_break_minutes}m
            </span>
          </div>
        </div>
      </section>

      <div className="flex gap-2 overflow-x-auto pb-1">
        {dates.map((date, index) => {
          const count = plan.tasks.filter(
            (task) => task.scheduled_date === date,
          ).length;
          const active = date === selectedDate;
          return (
            <button
              key={date}
              type="button"
              onClick={() => onSelectedDate(date)}
              className={`min-w-[92px] rounded-[var(--radius-md)] border px-3 py-2.5 text-left transition ${
                active
                  ? "border-[var(--accent)] bg-[var(--surface-raised)]"
                  : "border-[var(--border)] bg-[var(--surface)]"
              }`}
            >
              <b className="block text-sm">Day {index + 1}</b>
              <span className="mt-0.5 block text-xs text-[var(--foreground-muted)]">
                {date.slice(5)}
              </span>
              <span className="mt-1 block text-[11px] text-[var(--foreground-muted)]">
                {count ? `${count} 项` : "休息 / 待安排"}
              </span>
            </button>
          );
        })}
      </div>

      <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4 sm:p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs text-[var(--foreground-muted)]">
              {selectedDate}
            </p>
            <h3 className="mt-1 text-lg font-semibold">
              Day {dayIndex + 1}
            </h3>
            <p className="mt-1 text-sm text-[var(--foreground-muted)]">
              {tasks.length
                ? `${dayCompleted}/${tasks.length} 项完成`
                : "今天暂未安排任务"}
            </p>
          </div>
          <div className="flex min-w-[260px] flex-1 justify-end gap-2">
            <input
              value={newTaskTitle}
              onChange={(event) => onNewTaskTitle(event.target.value)}
              placeholder="给这一天添加任务"
              className="min-w-0 max-w-sm flex-1 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
            />
            <PrimaryButton onClick={onCreateTask} disabled={creatingTask}>
              添加
            </PrimaryButton>
          </div>
        </div>

        {taskError ? (
          <p className="mt-2 text-sm text-red-500">
            {messageOf(taskError)}
          </p>
        ) : null}

        <div className="mt-4 space-y-3">
          {tasks.map((task) => (
            <DayTaskCard
              key={task.id}
              task={task}
              planId={plan.id}
              editing={taskEditingId === task.id}
              draft={taskEditingId === task.id ? taskDraft : null}
              onEdit={() => onStartTaskEdit(task)}
              onDraft={onTaskDraft}
              onSave={onSaveTask}
              onCancel={onCancelTaskEdit}
              saving={savingTask}
              saveError={
                taskEditingId === task.id ? taskSaveError : null
              }
              onStatus={(status) => onTaskStatus(task.id, status)}
              onDelete={() => onDeleteTask(task.id)}
              onFocus={() => onFocusTask(task)}
            />
          ))}
          {!tasks.length ? (
            <div className="rounded-[var(--radius-md)] border border-dashed border-[var(--border-strong)] px-5 py-10 text-center">
              <p className="text-sm font-medium">今天可以留白</p>
              <p className="mt-1 text-xs text-[var(--foreground-muted)]">
                没有任务时不自动编造学习内容；需要时再添加。
              </p>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function DayTaskCard({
  task,
  planId,
  editing,
  draft,
  onEdit,
  onDraft,
  onSave,
  onCancel,
  saving,
  saveError,
  onStatus,
  onDelete,
  onFocus,
}: {
  task: StudyTask;
  planId: string;
  editing: boolean;
  draft: TaskDraft | null;
  onEdit: () => void;
  onDraft: (draft: TaskDraft | null) => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  saveError: unknown;
  onStatus: (status: StudyTaskStatus) => void;
  onDelete: () => void;
  onFocus: () => void;
}) {
  const done = task.status === "completed";
  return (
    <article
      className={`rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] p-4 ${
        done ? "opacity-70" : ""
      }`}
    >
      <div className="flex gap-3">
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
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--foreground-muted)]">
                <span>{task.planned_minutes} 分钟</span>
                <span>{taskStatusText(task.status)}</span>
                {task.review_required ? (
                  <span>↻ 需要复习</span>
                ) : null}
              </div>
            </div>

            {!editing ? (
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={onFocus}
                  className="text-xs font-medium text-[var(--accent)]"
                >
                  🍅 专注
                </button>
                <button
                  type="button"
                  onClick={onEdit}
                  className="text-xs text-[var(--foreground-muted)] hover:text-[var(--foreground)]"
                >
                  编辑
                </button>
                <button
                  type="button"
                  onClick={onDelete}
                  className="text-xs text-[var(--foreground-muted)] hover:text-red-500"
                >
                  删除
                </button>
              </div>
            ) : null}
          </div>

          {editing && draft ? (
            <div className="mt-3 grid gap-2 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-raised)] p-3">
              <input
                value={draft.title}
                onChange={(e) =>
                  onDraft({ ...draft, title: e.target.value })
                }
                className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
              />
              <textarea
                value={draft.description}
                onChange={(e) =>
                  onDraft({ ...draft, description: e.target.value })
                }
                rows={2}
                placeholder="任务说明"
                className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
              />
              <div className="grid gap-2 sm:grid-cols-3">
                <input
                  type="date"
                  value={draft.scheduled_date}
                  onChange={(e) =>
                    onDraft({
                      ...draft,
                      scheduled_date: e.target.value,
                    })
                  }
                  className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
                />
                <input
                  type="number"
                  min={1}
                  value={draft.planned_minutes}
                  onChange={(e) =>
                    onDraft({
                      ...draft,
                      planned_minutes: e.target.value,
                    })
                  }
                  className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
                />
                <select
                  value={draft.status}
                  onChange={(e) =>
                    onDraft({
                      ...draft,
                      status: e.target.value as StudyTaskStatus,
                    })
                  }
                  className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2 text-sm"
                >
                  <option value="planned">计划中</option>
                  <option value="in_progress">进行中</option>
                  <option value="completed">已完成</option>
                  <option value="skipped">已跳过</option>
                  <option value="deferred">已顺延</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-xs text-[var(--foreground-muted)]">
                <input
                  type="checkbox"
                  checked={draft.review_required}
                  onChange={(e) =>
                    onDraft({
                      ...draft,
                      review_required: e.target.checked,
                    })
                  }
                />
                需要复习
              </label>
              <div className="flex gap-2">
                <SecondaryButton onClick={onSave}>
                  {saving ? "保存中…" : "保存任务"}
                </SecondaryButton>
                <SecondaryButton onClick={onCancel}>
                  取消
                </SecondaryButton>
              </div>
              {saveError ? (
                <p className="text-xs text-red-500">
                  {messageOf(saveError)}
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
      <TaskReminderControl planId={planId} task={task} />
    </article>
  );
}

function ToolRail({
  drawer,
  onDrawer,
}: {
  drawer: DrawerKind;
  onDrawer: (drawer: DrawerKind) => void;
}) {
  const tools: Array<{
    key: Exclude<DrawerKind, null>;
    icon: string;
    label: string;
  }> = [
    { key: "library", icon: "📚", label: "资料" },
    { key: "textbook", icon: "📖", label: "教材" },
    { key: "review", icon: "🧠", label: "复习" },
    { key: "qa", icon: "❓", label: "答疑" },
  ];

  return (
    <nav
      aria-label="学习工具"
      className="fixed right-3 top-1/2 z-30 flex -translate-y-1/2 flex-col gap-2"
    >
      {tools.map((tool) => (
        <button
          key={tool.key}
          type="button"
          aria-label={tool.label}
          title={tool.label}
          onClick={() =>
            onDrawer(drawer === tool.key ? null : tool.key)
          }
          className={`flex h-11 w-11 items-center justify-center rounded-full border shadow-sm ${
            drawer === tool.key
              ? "border-[var(--accent)] bg-[var(--surface-raised)]"
              : "border-[var(--border)] bg-[var(--surface-raised)]"
          }`}
        >
          {tool.icon}
        </button>
      ))}
    </nav>
  );
}

function UtilityDrawer({
  kind,
  onClose,
  todayTasks,
  planId,
}: {
  kind: Exclude<DrawerKind, null>;
  onClose: () => void;
  todayTasks: StudyTask[];
  planId?: string;
}) {
  if (kind === "qa") return <StudyQuestionDialog onClose={onClose} />;

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/10"
      onMouseDown={onClose}
    >
      <aside
        className="h-full w-full max-w-xl overflow-y-auto border-l border-[var(--border)] bg-[var(--background)] p-5 shadow-xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {kind === "library" ? "学习资料" : kind === "textbook" ? "教材采集" : "复习"}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-[var(--foreground-muted)]"
          >
            收起
          </button>
        </div>

        {kind === "library" ? (
          <StudyLibraryPanel />
        ) : kind === "textbook" ? (
          <StudyTextbookPanel />
        ) : (
          <StudyReviewPanel todayTasks={todayTasks} planId={planId} />
        )}
      </aside>
    </div>
  );
}

function FloatingPomodoro({
  plan,
  task,
  open,
  onOpen,
}: {
  plan: StudyPlan;
  task?: StudyTask;
  open: boolean;
  onOpen: (open: boolean) => void;
}) {
  const qc = useQueryClient();
  const taskId = task?.id ?? "";
  const sessionsKey = ["study", "sessions", taskId] as const;
  const pomodoroKey = ["study", "pomodoro", plan.id] as const;

  const sessionsQuery = useQuery({
    queryKey: sessionsKey,
    queryFn: () => listStudySessions(plan.id, taskId),
    enabled: Boolean(taskId),
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
    if (taskId) qc.invalidateQueries({ queryKey: sessionsKey });
    qc.invalidateQueries({ queryKey: pomodoroKey });
  };

  const create = useMutation({
    mutationFn: () => {
      if (!task) throw new Error("请先选择一个任务");
      return createStudySession(plan.id, task.id, {
        session_type: pomodoro?.next_session_type,
      });
    },
    onSuccess: refresh,
  });
  const start = useMutation({
    mutationFn: startStudySession,
    onSuccess: refresh,
  });
  const pause = useMutation({
    mutationFn: pauseStudySession,
    onSuccess: refresh,
  });
  const resume = useMutation({
    mutationFn: resumeStudySession,
    onSuccess: refresh,
  });
  const complete = useMutation({
    mutationFn: completeStudySession,
    onSuccess: refresh,
  });
  const abandon = useMutation({
    mutationFn: abandonStudySession,
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

  const nextType = pomodoro?.next_session_type ?? "focus";
  const blockedByOtherSession =
    Boolean(pomodoro?.current_session_id) &&
    pomodoro?.current_session_id !== activeSession?.id;
  const cannotCreateFocus = Boolean(
    task?.status === "completed" && nextType === "focus",
  );

  if (!open) {
    return (
      <button
        type="button"
        aria-label="番茄钟"
        title="番茄钟"
        onClick={() => onOpen(true)}
        className="fixed bottom-5 right-4 z-30 flex h-14 min-w-14 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--surface-raised)] px-3 text-lg shadow-lg"
      >
        🍅
      </button>
    );
  }

  return (
    <aside className="fixed bottom-5 right-4 z-50 w-[min(92vw,360px)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4 shadow-xl">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.14em] text-[var(--foreground-muted)]">
            Classic Pomodoro
          </p>
          <h3 className="mt-1 truncate font-semibold">
            {task?.title ?? "先从任务卡选择一个任务"}
          </h3>
        </div>
        <button
          type="button"
          onClick={() => onOpen(false)}
          className="text-xs text-[var(--foreground-muted)]"
        >
          收起
        </button>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-[128px_minmax(0,1fr)] sm:items-center">
        <PomodoroClock
          session={activeSession}
          defaultMinutes={pomodoro?.next_minutes ?? plan.focus_minutes}
          nextType={nextType}
          compact
        />
        <div>
          <p className="text-sm text-[var(--foreground-muted)]">
            {task
              ? pomodoroHint(activeSession, pomodoro)
              : "先点击某个任务的“🍅 专注”，再开始计时。"}
          </p>

          <div className="mt-3 flex flex-wrap gap-2">
            {!activeSession ? (
              <PrimaryButton
                disabled={
                  busy ||
                  !task ||
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
        </div>
      </div>

      {blockedByOtherSession ? (
        <p className="mt-3 text-xs text-[var(--foreground-muted)]">
          当前计划已有另一个番茄会话，请先结束它。
        </p>
      ) : null}
      {cannotCreateFocus ? (
        <p className="mt-3 text-xs text-[var(--foreground-muted)]">
          该任务已完成；请选择尚未完成的任务开始下一轮专注。
        </p>
      ) : null}
      {error ? (
        <p className="mt-3 text-sm text-red-500">
          {messageOf(error)}
        </p>
      ) : null}
    </aside>
  );
}

function PomodoroClock({
  session,
  defaultMinutes,
  nextType,
  compact = false,
}: {
  session?: StudySession;
  defaultMinutes: number;
  nextType: StudySession["session_type"];
  compact?: boolean;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const { remainingSeconds, totalSeconds } = useMemo(() => {
    const total = Math.max(
      1,
      (session?.planned_minutes ?? defaultMinutes) * 60,
    );

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
  const elapsed = Math.min(
    totalSeconds,
    Math.max(0, totalSeconds - remainingSeconds),
  );
  const progress = Math.round((elapsed / totalSeconds) * 100);
  const size = compact ? "h-28 w-28" : "h-40 w-40";
  const text = compact ? "text-2xl" : "text-3xl";

  return (
    <div className="flex justify-center">
      <div
        className={`relative flex ${size} shrink-0 items-center justify-center rounded-full`}
        style={{
          background: `conic-gradient(var(--accent) ${progress}%, var(--border) ${progress}% 100%)`,
        }}
      >
        <div className="absolute inset-[6px] rounded-full bg-[var(--surface-raised)]" />
        <div className="relative z-10 text-center">
          <p
            className={`font-mono ${text} font-semibold tabular-nums tracking-tight`}
          >
            {String(minutes).padStart(2, "0")}:
            {String(seconds).padStart(2, "0")}
          </p>
          <p className="mt-1 text-xs text-[var(--foreground-muted)]">
            {session
              ? sessionStatusText(
                  session.status,
                  session.session_type,
                )
              : sessionTypeText(nextType)}
          </p>
        </div>
      </div>
    </div>
  );
}

function ImportPreviewDialog({
  plan,
  fileName,
  busy,
  error,
  onCancel,
  onConfirm,
}: {
  plan: StudyPlan;
  fileName: string;
  busy: boolean;
  error: unknown;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [date, setDate] = useState(() => chooseInitialDate(plan));
  const dates = useMemo(
    () => dateRange(plan.start_date, plan.end_date),
    [plan.start_date, plan.end_date],
  );
  const tasks = plan.tasks
    .filter((task) => task.scheduled_date === date)
    .sort((a, b) => a.order_index - b.order_index);
  const dayNo = Math.max(0, dates.indexOf(date)) + 1;

  return (
    <div className="fixed inset-0 z-[70] overflow-y-auto bg-black/30 p-4 sm:p-8">
      <div className="mx-auto max-w-4xl rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--background)] p-5 shadow-2xl sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs text-[var(--foreground-muted)]">
              Markdown 导入预览 · {fileName || "study_plan.md"}
            </p>
            <h2 className="mt-1 text-xl font-semibold">{plan.title}</h2>
            <p className="mt-1 text-sm text-[var(--foreground-muted)]">
              {plan.start_date} → {plan.end_date} · {plan.tasks.length} 个任务
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="text-sm text-[var(--foreground-muted)]"
          >
            关闭
          </button>
        </div>

        {plan.goals.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {plan.goals.map((goal) => (
              <span
                key={goal}
                className="rounded-full bg-[var(--surface)] px-3 py-1.5 text-xs"
              >
                {goal}
              </span>
            ))}
          </div>
        ) : null}

        <div className="mt-5 flex gap-2 overflow-x-auto pb-1">
          {dates.map((item, index) => (
            <button
              key={item}
              type="button"
              onClick={() => setDate(item)}
              className={`min-w-[88px] rounded-[var(--radius-md)] border px-3 py-2 text-left ${
                item === date
                  ? "border-[var(--accent)] bg-[var(--surface-raised)]"
                  : "border-[var(--border)] bg-[var(--surface)]"
              }`}
            >
              <b className="block text-sm">Day {index + 1}</b>
              <span className="text-xs text-[var(--foreground-muted)]">
                {item.slice(5)}
              </span>
            </button>
          ))}
        </div>

        <section className="mt-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4">
          <h3 className="font-semibold">
            Day {dayNo} · {date}
          </h3>
          <div className="mt-3 space-y-2">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="rounded-[var(--radius-md)] bg-[var(--surface)] p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">{task.title}</p>
                    {task.description ? (
                      <p className="mt-1 text-sm text-[var(--foreground-muted)]">
                        {task.description}
                      </p>
                    ) : null}
                  </div>
                  <span className="shrink-0 text-xs text-[var(--foreground-muted)]">
                    {task.planned_minutes}m
                  </span>
                </div>
                {task.review_required ? (
                  <p className="mt-2 text-xs text-[var(--foreground-muted)]">
                    ↻ 需要复习
                  </p>
                ) : null}
              </div>
            ))}
            {!tasks.length ? (
              <p className="py-6 text-center text-sm text-[var(--foreground-muted)]">
                这一天没有任务。
              </p>
            ) : null}
          </div>
        </section>

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <SecondaryButton onClick={onCancel}>取消</SecondaryButton>
          <PrimaryButton onClick={onConfirm} disabled={busy}>
            {busy ? "导入中…" : "确认导入"}
          </PrimaryButton>
        </div>

        {error ? (
          <p className="mt-3 text-right text-sm text-red-500">
            {messageOf(error)}
          </p>
        ) : null}
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
        展开“计划管理”新建计划，或导入 canonical StudyPlan Markdown。
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
      className={`rounded-[var(--radius-md)] border px-3 py-2 text-sm disabled:opacity-50 ${
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
  if (status === "running") {
    return type === "focus" ? "专注中" : `${noun}中`;
  }
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
      ? "点击“开始专注”后进入计时；完成后按计划进入休息。"
      : "休息计时已经准备好，点击开始即可。";
  }
  if (session?.status === "running") {
    return session.session_type === "focus"
      ? "保持当前节奏；可以把窗口收起，服务器继续记录时间。"
      : "暂时离开任务，让注意力恢复。";
  }
  if (session?.status === "paused") {
    return "当前已暂停；继续后从剩余时间恢复。";
  }
  if (!state) return "经典节奏默认 25 分钟专注、5 分钟短休息。";
  if (state.next_session_type === "long_break") {
    return `已完成 ${state.focuses_in_cycle}/${state.cycle_length} 个番茄，下一步是长休息。`;
  }
  if (state.next_session_type === "short_break") {
    return `完成一个番茄后，进行 ${state.next_minutes} 分钟短休息。`;
  }
  return `下一轮 ${state.next_minutes} 分钟专注；第 ${state.cycle_length} 个番茄后进入长休息。`;
}

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <section className="mx-auto w-full max-w-6xl px-5 py-7 pr-16 sm:px-8 sm:py-9 sm:pr-20">
      {children}
    </section>
  );
}


function TaskReminderControl({ planId, task }: { planId: string; task: StudyTask }) {
  const cache = useQueryClient();
  const queryKey = ["study-reminders", planId];
  const saved = useQuery({
    queryKey,
    queryFn: () => listStudyReminders(planId),
  });
  const value = saved.data?.reminders[task.id] || "";
  const [draft, setDraft] = useState<string>();
  const mutation = useMutation({
    mutationFn: async (time: string | null) => {
      const sessionId = time ? (await fetchCompanionBootstrap()).session_id : undefined;
      return setStudyReminder(planId, task.id, time, sessionId);
    },
    onSuccess: ({ time }) => {
      cache.setQueryData<{ reminders: Record<string, string> }>(queryKey, previous => ({
        reminders: { ...previous?.reminders, [task.id]: time || "" },
      }));
      setDraft(undefined);
    },
  });
  return <details className="mt-2 text-sm">
    <summary>{value ? "学习提醒 · " + value : "设置学习提醒"}</summary>
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <label>任务当天 <input type="time" aria-label="学习提醒时刻" value={draft ?? value}
        disabled={mutation.isPending} onChange={event => setDraft(event.target.value)} /></label>
      <SecondaryButton disabled={!(draft ?? value) || mutation.isPending}
        onClick={() => mutation.mutate(draft ?? value)}>保存提醒</SecondaryButton>
      {value && <SecondaryButton disabled={mutation.isPending} onClick={() => mutation.mutate(null)}>取消提醒</SecondaryButton>}
    </div>
    {(mutation.error || saved.error) && <p role="alert">{messageOf(mutation.error || saved.error)}</p>}
  </details>;
}
