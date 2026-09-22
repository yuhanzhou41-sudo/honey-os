import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StudyPlan } from "../../api/study";
import { StudyPage } from "./StudyPage";

const {
  listStudyPlans,
  updateStudyPlan,
  updateStudyTask,
  listStudySessions,
  getStudyPomodoroState,
} = vi.hoisted(() => ({
  listStudyPlans: vi.fn(),
  updateStudyPlan: vi.fn(),
  updateStudyTask: vi.fn(),
  listStudySessions: vi.fn(),
  getStudyPomodoroState: vi.fn(),
}));

vi.mock("../../api/study", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/study")>();
  return {
    ...actual,
    listStudyPlans,
    updateStudyPlan,
    updateStudyTask,
    listStudySessions,
    getStudyPomodoroState,
  };
});

const plan: StudyPlan = {
  id: "plan_phase51",
  schema_version: 1,
  title: "Phase 5 plan",
  description: "Original description",
  start_date: "2026-09-22",
  end_date: "2026-09-28",
  status: "draft",
  focus_minutes: 25,
  break_minutes: 5,
  long_break_minutes: 15,
  long_break_after_sessions: 4,
  source_type: "manual",
  goals: ["Goal A"],
  tasks: [
    {
      id: "task_phase51",
      plan_id: "plan_phase51",
      title: "Original task",
      description: "Task description",
      scheduled_date: "2026-09-23",
      planned_minutes: 30,
      status: "planned",
      order_index: 1,
      review_required: false,
      created_at: "2026-09-22T00:00:00Z",
      updated_at: "2026-09-22T00:00:00Z",
    },
  ],
  created_at: "2026-09-22T00:00:00Z",
  updated_at: "2026-09-22T00:00:00Z",
};

function renderStudyPage() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <StudyPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  vi.clearAllMocks();
  listStudyPlans.mockResolvedValue({ plans: [plan] });
  listStudySessions.mockResolvedValue({ sessions: [] });
  getStudyPomodoroState.mockResolvedValue({
    pomodoro: {
      focuses_in_cycle: 0,
      cycle_length: 4,
      next_session_type: "focus",
      next_minutes: 25,
      current_session_id: null,
      current_session_type: null,
      current_session_status: null,
    },
  });
  updateStudyPlan.mockResolvedValue({
    plan: { ...plan, title: "Edited plan" },
  });
  updateStudyTask.mockResolvedValue({
    plan: {
      ...plan,
      tasks: [{ ...plan.tasks[0], title: "Edited task", review_required: true }],
    },
  });
});

describe("StudyPage Phase 5.1 manual editor", () => {
  it("edits and saves canonical StudyPlan fields", async () => {
    renderStudyPage();

    expect(await screen.findByRole("heading", { level: 2, name: "Phase 5 plan" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑计划" }));

    const titleInput = screen
      .getAllByDisplayValue("Phase 5 plan")
      .find((element) => element.tagName === "INPUT") as HTMLInputElement;
    fireEvent.change(titleInput, { target: { value: "Edited plan" } });

    const description = screen.getByPlaceholderText("计划说明");
    fireEvent.change(description, { target: { value: "Edited description" } });

    const goals = screen.getByPlaceholderText("学习目标，每行一个");
    fireEvent.change(goals, { target: { value: "Goal A\nGoal B" } });

    fireEvent.click(screen.getByRole("button", { name: "保存计划" }));

    await waitFor(() => {
      expect(updateStudyPlan).toHaveBeenCalledWith(
        "plan_phase51",
        expect.objectContaining({
          title: "Edited plan",
          description: "Edited description",
          start_date: "2026-09-22",
          end_date: "2026-09-28",
          goals: ["Goal A", "Goal B"],
          focus_minutes: 25,
          break_minutes: 5,
          long_break_minutes: 15,
          long_break_after_sessions: 4,
          status: "draft",
        }),
      );
    });
  });

  it("edits and saves canonical StudyTask fields", async () => {
    renderStudyPage();

    expect(await screen.findByText("Original task")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑" }));

    const titleInput = screen.getByDisplayValue("Original task");
    fireEvent.change(titleInput, { target: { value: "Edited task" } });

    const taskDescription = screen.getByPlaceholderText("任务说明");
    fireEvent.change(taskDescription, {
      target: { value: "Edited task description" },
    });

    const review = screen.getByRole("checkbox", { name: "需要复习" });
    fireEvent.click(review);

    fireEvent.click(screen.getByRole("button", { name: "保存任务" }));

    await waitFor(() => {
      expect(updateStudyTask).toHaveBeenCalledWith(
        "plan_phase51",
        "task_phase51",
        expect.objectContaining({
          title: "Edited task",
          description: "Edited task description",
          scheduled_date: "2026-09-23",
          planned_minutes: 30,
          review_required: true,
          status: "planned",
        }),
      );
    });
  });
});

describe("StudyPage Phase 5.3B adaptive workspace", () => {
  it("keeps plan-first UI with reserved compact tools", async () => {
    renderStudyPage();

    expect(
      await screen.findByRole("heading", { level: 2, name: "Phase 5 plan" }),
    ).toBeInTheDocument();
    expect(screen.getByText("阳光点")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "资料" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "复习" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "答疑" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "番茄钟" })).toBeInTheDocument();
  });

  it("opens one floating Pomodoro from a task", async () => {
    renderStudyPage();

    expect(await screen.findByText("Original task")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "🍅 专注" }));

    expect(screen.getByText("Classic Pomodoro")).toBeInTheDocument();
    expect(
      screen.getByText("Original task", { selector: "h3" }),
    ).toBeInTheDocument();
    expect(screen.getByText("25:00")).toBeInTheDocument();
  });
});
