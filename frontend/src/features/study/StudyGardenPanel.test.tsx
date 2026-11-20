import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { getGardenSummary, getStudyGarden, type GardenPlant } from "../../api/study-growth";
import StudyGardenPanel from "./StudyGardenPanel";

vi.mock("../../api/study-growth", () => ({ getStudyGarden: vi.fn(), getGardenSummary: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("shows growing and planted flowers with calendar summaries and daily memory", async () => {
  const base = { plant: "幼苗", enabled: true, closed: false, planted: false, sunlight: 20,
    standard_days: 3, tasks: 10, completed: 4, as_of: "2026-11-20", summary: null };
  vi.mocked(getStudyGarden).mockResolvedValue({ plants: [
    { ...base, plan_id: "active", title: "Dermatology" } as GardenPlant,
    { ...base, plan_id: "finished", title: "Finished course", planted: true, closed: true,
      summary: "该计划已完成。" } as GardenPlant,
  ] });
  vi.mocked(getGardenSummary).mockImplementation(async (planId, period) => ({
    plan_id: planId, period, start_date: "2026-11-01", end_date: "2026-11-30", as_of: "2026-11-20",
    archived: planId === "finished", body: "真实学习统计", stats: {}, final_summary: null,
    days: [{ date: "2026-11-20", tasks: 1, completed: 1, focus_minutes: 25, attempts: 0,
      correct: 0, recalls: 0, mastered: 0, reward_points: 20, sources: { tasks: ["task1"] } }],
  }));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><StudyGardenPanel standalone /></QueryClientProvider>);
  expect(await screen.findByText("生长中 · 幼苗")).toBeInTheDocument();
  expect(screen.getByText("已种入花园 · 纪念花")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Finished course/ }));
  expect(await screen.findByText("该计划已完成。")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "月总结" }));
  await waitFor(() => expect(getGardenSummary).toHaveBeenLastCalledWith("finished", "month", expect.any(String)));
  fireEvent.click(screen.getByRole("button", { name: "年总结" }));
  await waitFor(() => expect(getGardenSummary).toHaveBeenLastCalledWith("finished", "year", expect.any(String)));
  expect(await screen.findByText(/结束时留存/)).toBeInTheDocument();
  expect(screen.getByText(/每日学习记忆与来源/)).toBeInTheDocument();
});
