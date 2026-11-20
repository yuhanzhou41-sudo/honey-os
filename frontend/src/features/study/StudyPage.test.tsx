import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { StudyPlan } from "../../api/study";
import { studyReview } from "../../api/study-review";
import StudyReviewPanel from "./StudyReviewPanel";
import QuestionIntakePanel from "./QuestionIntakePanel";
import { StudyPage } from "./StudyPage";

const {
  previewStudyPlanMarkdown,
  listStudyPlans,
  updateStudyPlan,
  updateStudyTask,
  listStudySessions,
  getStudyPomodoroState,
} = vi.hoisted(() => ({
  previewStudyPlanMarkdown: vi.fn(),
  listStudyPlans: vi.fn(),
  updateStudyPlan: vi.fn(),
  updateStudyTask: vi.fn(),
  listStudySessions: vi.fn(),
  getStudyPomodoroState: vi.fn(),
}));

vi.mock("../../api/study-planning", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../api/study-planning")>(),
  confirmManualStudyChange: (id: string, patch: object, taskId?: string) =>
    taskId ? updateStudyTask(id, taskId, patch) : updateStudyPlan(id, patch),
}));

vi.mock("../../api/study", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/study")>();
  return {
    ...actual,
    previewStudyPlanMarkdown,
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
  vi.restoreAllMocks();
});

it("requires a recall response before revealing the evidence and records mastery", async () => {
  const card = {
    id: "card", front: "Carrier?", back: "ATP", excerpt: "ATP carries energy.",
    source_title: "Biology", resource_id: "bio", question_id: null,
  };
  const recall = {
    id: "recall", card_id: card.id, response: "ATP", created_at: "2026-11-17T00:00:00Z",
    rating: null, due_at: null,
  };
  vi.spyOn(studyReview, "questions").mockResolvedValue({ questions: [] });
  vi.spyOn(studyReview, "cards").mockResolvedValue({ cards: [] });
  vi.spyOn(studyReview, "draw").mockResolvedValue({ card: { id: card.id, front: card.front }, matched: 1 });
  const submit = vi.spyOn(studyReview, "recall").mockResolvedValue({ card, recall });
  const rate = vi.spyOn(studyReview, "rate").mockResolvedValue({
    ...recall, rating: 2, due_at: "2026-11-20T00:00:00Z",
  });
  render(<StudyReviewPanel todayTasks={plan.tasks} />);
  fireEvent.click(screen.getByRole("button", { name: "今日复习" }));
  fireEvent.change(screen.getByLabelText("从今日任务填写知识点"), { target: { value: plan.tasks[0].id } });
  expect(screen.getByLabelText("知识点", { exact: true })).toHaveValue(plan.tasks[0].title);
  fireEvent.click(screen.getByRole("button", { name: "抽背到期闪卡" }));
  expect(await screen.findByText("Carrier?")).toBeInTheDocument();
  expect(screen.queryByText("ATP carries energy.")).toBeNull();
  expect(screen.getByRole("button", { name: "提交复述并核对" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("先复述你的答案"), { target: { value: "ATP" } });
  fireEvent.click(screen.getByRole("button", { name: "提交复述并核对" }));
  expect(await screen.findByText("ATP carries energy.")).toBeInTheDocument();
  expect(submit).toHaveBeenCalledWith(card.id, expect.any(String), "ATP", undefined);
  fireEvent.click(screen.getByRole("button", { name: "已掌握" }));
  expect(await screen.findByText(/下次复习/)).toBeInTheDocument();
  expect(rate).toHaveBeenCalledWith(recall.id, 2, undefined);
});

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
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

it("asks for permission before generating after an empty search and supports direct generation", async () => {
  const draft = {
    source: { id: "mock", kind: "mock" as const, title: "Cell biology", url: null },
    text: "Cell biology", segments: 1,
    questions: [{ prompt: "Carrier?", options: ["ATP", "DNA"], correct: 0, excerpt: "Cell biology", explanation: "" }],
  };
  vi.spyOn(studyReview, "searchExams").mockResolvedValue({ sources: [] });
  const generate = vi.spyOn(studyReview, "practiceDrafts").mockResolvedValue(draft);
  render(<QuestionIntakePanel planId={plan.id} tasks={plan.tasks} onSaved={async () => {}} />);
  fireEvent.click(screen.getByText("添加练习题"));
  fireEvent.click(screen.getByRole("button", { name: "联网找真题" }));
  fireEvent.change(screen.getByLabelText("真题主题"), { target: { value: "细胞生物学" } });
  fireEvent.click(screen.getByRole("button", { name: "搜索真题" }));
  const consent = await screen.findByRole("button", { name: "同意并生成模拟题" });
  expect(generate).not.toHaveBeenCalled();
  fireEvent.click(consent);
  expect(await screen.findByText("模拟题草稿")).toBeInTheDocument();
  expect(generate).toHaveBeenLastCalledWith("细胞生物学", plan.id, [plan.tasks[0].id]);
  fireEvent.click(screen.getByRole("button", { name: "AI 出模拟题" }));
  fireEvent.click(screen.getByRole("button", { name: "生成模拟题" }));
  expect(await screen.findByText("模拟题草稿")).toBeInTheDocument();
  expect(generate).toHaveBeenCalledTimes(2);
});

it("accepts a pasted screenshot and requires an answer before saving the extracted exercise", async () => {
  const draft = {
    source: { id: "upload", kind: "upload" as const, title: "capture.png", url: null },
    text: "Carrier? A. ATP B. DNA", segments: 1,
    questions: [{ prompt: "Carrier?", options: ["ATP", "DNA"], correct: null,
      excerpt: "Carrier? A. ATP B. DNA", explanation: "" }],
  };
  const upload = vi.spyOn(studyReview, "uploadDrafts").mockResolvedValue(draft);
  const save = vi.spyOn(studyReview, "saveIntake").mockResolvedValue({ imported: 1 });
  render(<QuestionIntakePanel tasks={[]} onSaved={async () => {}} />);
  fireEvent.click(screen.getByText("添加练习题"));
  const screenshot = new File(["fake"], "capture.png", { type: "image/png" });
  fireEvent.paste(screen.getByLabelText("粘贴截图"), { clipboardData: {
    items: [{ type: "image/png", getAsFile: () => screenshot }],
  } });
  fireEvent.click(screen.getByRole("button", { name: "提取题目" }));
  const confirm = await screen.findByRole("button", { name: "确认入库" });
  expect(upload).toHaveBeenCalledWith("capture.png", expect.any(String), 1);
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText("正确选项"), { target: { value: "0" } });
  fireEvent.click(confirm);
  expect(await screen.findByText("已入库 1 道题。")).toBeInTheDocument();
  expect(save).toHaveBeenCalledWith("upload", [{ ...draft.questions[0], correct: 0 }]);
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
    expect(screen.getByRole("button", { name: "教材" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "校园" })).toBeInTheDocument();
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



it("shows V2 minimum tasks and flex time separately", async () => {
  const task = {
    ...plan.tasks[0], priority: "must" as const,
    minimum_required: true, kind: "flashcard" as const,
  };
  listStudyPlans.mockResolvedValue({ plans: [{
    ...plan, schema_version: 2, tasks: [task],
    flex_slots: [{
      id: "flex_preview", scheduled_date: task.scheduled_date, planned_minutes: 30,
    }],
  }] });
  renderStudyPage();
  expect(await screen.findByText(/必做 · 闪卡 · 保底任务/)).toBeInTheDocument();
  expect(screen.getByRole("list", { name: "机动时间" })).toHaveTextContent("机动时间 30 分钟");
});



it("keeps the newest file preview when an earlier response arrives late", async () => {
  let resolveFirst!: (value: { plan: StudyPlan }) => void;
  previewStudyPlanMarkdown.mockImplementation((markdown: string) => markdown === "first"
    ? new Promise(resolve => { resolveFirst = resolve; })
    : Promise.resolve({ plan: { ...plan, title: "Second preview" } }));
  renderStudyPage();
  await screen.findByText("Original task");
  const input = document.querySelector('input[accept=".md,text/markdown,text/plain"]') as HTMLInputElement;
  const first = new File(["first"], "first.md");
  const second = new File(["second"], "second.md");
  Object.defineProperty(first, "text", { value: async () => "first" });
  Object.defineProperty(second, "text", { value: async () => "second" });
  fireEvent.change(input, { target: { files: [first] } });
  await waitFor(() => expect(previewStudyPlanMarkdown).toHaveBeenCalledWith("first"));
  fireEvent.change(input, { target: { files: [second] } });
  await screen.findByRole("heading", { name: "Second preview" });
  await act(async () => { resolveFirst({ plan: { ...plan, title: "First preview" } }); });
  expect(screen.queryByRole("heading", { name: "First preview" })).toBeNull();
  expect(screen.getByRole("heading", { name: "Second preview" })).toBeInTheDocument();
});


it("offers exactly the new V2 template and selected current plan downloads", async () => {
  const { container } = renderStudyPage();
  await screen.findByText("Phase 5 plan", { selector: "h2" });
  const downloads = Array.from(container.querySelectorAll<HTMLAnchorElement>("a[download]"));
  expect(downloads).toHaveLength(2);
  expect(downloads.find(link => link.textContent?.includes("新计划模板"))?.getAttribute("href"))
    .toBe("/api/study/plans/template?version=2");
  expect(downloads.find(link => link.textContent?.includes("当前计划"))?.getAttribute("href"))
    .toBe("/api/study/plans/plan_phase51/markdown");
  expect(container.textContent).not.toContain("下载 V1 模板");
  expect(container.textContent).not.toContain("下载编写指南");
});


it("keeps the imported plan selected across remount and slow loading", async () => {
  const imported = { ...plan, id: "plan_imported", title: "Imported dermatology" };
  listStudyPlans.mockResolvedValue({ plans: [plan, imported] });
  const first = renderStudyPage();
  await screen.findByText("Phase 5 plan", { selector: "h2" });
  fireEvent.click(screen.getByText(/计划管理/));
  const select = screen.getByRole("combobox", { name: "当前计划" });
  fireEvent.change(select, { target: { value: imported.id } });
  await screen.findByText(imported.title, { selector: "h2" });
  await waitFor(() => expect(localStorage.getItem("honeyos:study:selected-plan:default")).toBe(imported.id));
  first.unmount();
  let finish!: (value: { plans: StudyPlan[] }) => void;
  listStudyPlans.mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
  renderStudyPage();
  expect(localStorage.getItem("honeyos:study:selected-plan:default")).toBe(imported.id);
  await act(async () => finish({ plans: [plan, imported] }));
  expect(await screen.findByText(imported.title, { selector: "h2" })).toBeInTheDocument();
});

it("falls back when a remembered plan no longer exists", async () => {
  localStorage.setItem("honeyos:study:selected-plan:default", "deleted-plan");
  renderStudyPage();
  expect(await screen.findByText("Phase 5 plan", { selector: "h2" })).toBeInTheDocument();
  await waitFor(() => expect(localStorage.getItem("honeyos:study:selected-plan:default")).toBe(plan.id));
});


it("isolates remembered selections by profile", async () => {
  localStorage.setItem("honeyos:study:selected-plan:default", "default-plan");
  const before = window.location.pathname;
  window.history.replaceState({}, "", "/p/student/study");
  try {
    renderStudyPage();
    await screen.findByText("Phase 5 plan", { selector: "h2" });
    await waitFor(() => expect(localStorage.getItem("honeyos:study:selected-plan:/p/student")).toBe(plan.id));
    expect(localStorage.getItem("honeyos:study:selected-plan:default")).toBe("default-plan");
  } finally { window.history.replaceState({}, "", before); }
});
