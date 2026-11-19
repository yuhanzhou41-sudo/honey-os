import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { getCampusExams, refreshCampusExams, type CampusExams } from "../../api/campus";
import { StudyCampusPanel, examCountdown, extractExamDate } from "./StudyCampusPanel";

vi.mock("../../api/study", () => ({
  listStudyPlans: async () => ({
    plans: [{
      status: "active",
      tasks: [
        { id: "open", scheduled_date: "2099-01-01", status: "pending", title: "准备复习" },
        { id: "done", scheduled_date: "2099-01-02", status: "completed", title: "已结束任务" },
      ],
    }],
  }),
}));

vi.mock("../../api/campus", () => ({
  getCampusExams: vi.fn(),
  refreshCampusExams: vi.fn(),
}));

function examsFixture(overrides: Partial<CampusExams> = {}): { exams: CampusExams } {
  return {
    exams: {
      records: [],
      source: "https://jiaowu.cqmu.edu.cn:8080",
      captured_at: null,
      last_success_at: null,
      row_count: 0,
      has_data: false,
      stale: false,
      needs_capture: true,
      ...overrides,
    },
  };
}

function examDateFromToday(offsetDays: number): string {
  const target = new Date(Date.now() + offsetDays * 86_400_000);
  const iso = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai" }).format(target);
  return `${iso} 09:00-11:00`;
}

function renderPanel() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <StudyCampusPanel />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getCampusExams).mockResolvedValue(examsFixture());
  vi.mocked(refreshCampusExams).mockResolvedValue(examsFixture());
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

it("shows upcoming active Study tasks", async () => {
  renderPanel();

  expect(await screen.findByText("准备复习")).toBeInTheDocument();
  expect(screen.queryByText("已结束任务")).not.toBeInTheDocument();
});

it("renders exam rows with countdown chips and source line", async () => {
  vi.mocked(getCampusExams).mockResolvedValue(examsFixture({
    records: [
      {
        id: "exam_1", source: "https://jiaowu.cqmu.edu.cn:8080", batch_key: "2099-01-01",
        course: "外科学", exam_date: examDateFromToday(3), arrangement: "上午",
        location: "教学楼 301", captured_at: "2099-01-01T10:00:00+08:00",
      },
    ],
    row_count: 1, has_data: true, needs_capture: false,
    captured_at: "2099-01-01T10:00:00+08:00", last_success_at: "2099-01-01T10:00:00+08:00",
  }));

  renderPanel();

  expect(await screen.findByText("外科学")).toBeInTheDocument();
  expect(screen.getByText("3 天后")).toBeInTheDocument();
  expect(screen.getByText("教学楼 301")).toBeInTheDocument();
  expect(screen.getByText(/采集于 2099-01-01 10:00/)).toBeInTheDocument();
});

it("labels unparsed exam dates as unscheduled", async () => {
  vi.mocked(getCampusExams).mockResolvedValue(examsFixture({
    records: [
      {
        id: "exam_2", source: "https://jiaowu.cqmu.edu.cn:8080", batch_key: "2099-01-01",
        course: "妇产科学", exam_date: "时间未安排", arrangement: "时间未安排",
        location: "地点未安排", captured_at: "2099-01-01T10:00:00+08:00",
      },
    ],
    row_count: 1, has_data: true, needs_capture: false,
    captured_at: "2099-01-01T10:00:00+08:00", last_success_at: "2099-01-01T10:00:00+08:00",
  }));

  renderPanel();

  expect(await screen.findByText("妇产科学")).toBeInTheDocument();
  expect(screen.getByText("未排期")).toBeInTheDocument();
});

it("prompts to run the host when nothing has been captured", async () => {
  vi.mocked(getCampusExams).mockResolvedValue(examsFixture({ needs_capture: true }));

  renderPanel();

  expect(await screen.findByText(/尚未采集考试数据/)).toBeInTheDocument();
});

it("shows the confirmed-empty state when the school has no exams", async () => {
  vi.mocked(getCampusExams).mockResolvedValue(examsFixture({
    needs_capture: false, has_data: true, row_count: 0,
    captured_at: "2099-01-01T10:00:00+08:00", last_success_at: "2099-01-01T10:00:00+08:00",
  }));

  renderPanel();

  expect(await screen.findByText(/学校当前没有已安排的考试/)).toBeInTheDocument();
});

it("refresh pulls the newest snapshot into the card", async () => {
  vi.mocked(refreshCampusExams).mockResolvedValue(examsFixture({
    records: [
      {
        id: "exam_3", source: "https://jiaowu.cqmu.edu.cn:8080", batch_key: "2099-01-01",
        course: "内科学", exam_date: "2099-01-05 09:00", arrangement: "上午",
        location: "教学楼 202", captured_at: "2099-01-02T10:00:00+08:00",
      },
    ],
    row_count: 1, has_data: true, needs_capture: false,
    captured_at: "2099-01-02T10:00:00+08:00", last_success_at: "2099-01-02T10:00:00+08:00",
    result: "updated", imported: 1,
  }));

  renderPanel();
  fireEvent.click(await screen.findByRole("button", { name: "刷新" }));

  expect(await screen.findByText("内科学")).toBeInTheDocument();
  expect(refreshCampusExams).toHaveBeenCalledTimes(1);
});

it("extracts exam dates in different formats", () => {
  expect(extractExamDate("2026-11-25 09:00-11:00")).toBe("2026-11-25");
  expect(extractExamDate("2026/11/5 09:00")).toBe("2026-11-05");
  expect(extractExamDate("时间未安排")).toBeNull();
});

it("computes countdowns across month boundaries and same-day", () => {
  // 2026-11-30T20:00:00Z 是上海时间 2026-12-01 04:00
  expect(examCountdown("2026-12-03 09:00", new Date("2026-11-30T20:00:00Z"))).toBe(2);
  expect(examCountdown("2026-12-01 14:00", new Date("2026-12-01T02:00:00Z"))).toBe(0);
  expect(examCountdown("2026-11-30 09:00", new Date("2026-12-01T02:00:00Z"))).toBe(-1);
});
