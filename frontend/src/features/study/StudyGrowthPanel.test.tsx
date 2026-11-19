import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { StudyPlan } from "../../api/study";
import { getActivities, getGrowth, getSupervision, growthAction, setSupervision } from "../../api/study-growth";
import StudyGrowthPanel from "./StudyGrowthPanel";

vi.mock("../../api/study-growth", () => ({
  getGrowth: vi.fn(), getActivities: vi.fn(), getSupervision: vi.fn(), growthAction: vi.fn(),
  setSupervision: vi.fn(), getLearningDay: vi.fn(), getLearningWeek: vi.fn(), assignActivity: vi.fn(),
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); vi.restoreAllMocks(); });
const plan = {
  id: "plan_growth", schema_version: 2, title: "Practice", start_date: "2026-11-20", end_date: "2026-11-25",
  updated_at: "2026-11-20T00:00:00Z", tasks: [], flex_slots: [],
} as unknown as StudyPlan;
function setup(enabled: boolean) {
  vi.mocked(getGrowth).mockResolvedValue({ enabled, plan_id: plan.id, sunlight: 20, plant: "发芽", days: [],
    settings: { timezone: "Asia/Shanghai", minimum_mode: false } });
  vi.mocked(getActivities).mockResolvedValue({ events: [] });
  vi.mocked(getSupervision).mockResolvedValue({
    enabled: false, timezone: "Asia/Shanghai", quiet_start: 22, quiet_end: 8, remind_hour: 18, session_id: "",
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><StudyGrowthPanel plan={plan} onChanged={vi.fn()} /></QueryClientProvider>);
}
it("requires explicit activation and leaves supervision disabled", async () => {
  vi.mocked(growthAction).mockResolvedValue({});
  setup(false);
  await screen.findByText("发芽");
  expect(growthAction).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "启用本计划成长记录" }));
  await waitFor(() => expect(growthAction).toHaveBeenCalledWith(plan.id, "enable", {
    timezone: "Asia/Shanghai", minimum_mode: false,
  }));
  expect(setSupervision).not.toHaveBeenCalled();
});
it("cancelling final archive only previews and never closes", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  vi.mocked(growthAction).mockResolvedValue({
    summary: "该计划已主动停止。", reason: "stopped", expected_updated_at: "version", facts_revision: "facts",
  });
  setup(true);
  await screen.findByText("发芽");
  fireEvent.click(screen.getByText("保底、机动与学习记忆"));
  fireEvent.click(screen.getByRole("button", { name: "停止并归档" }));
  await waitFor(() => expect(window.confirm).toHaveBeenCalled());
  expect(growthAction).toHaveBeenCalledTimes(1);
  expect(growthAction).toHaveBeenCalledWith(plan.id, "close-preview", { reason: "stopped" });
});
