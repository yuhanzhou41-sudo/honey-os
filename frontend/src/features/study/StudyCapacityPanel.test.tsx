import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { getStudyCapacity, setStudyDailyCapacity, type StudyPlan } from "../../api/study";
import StudyCapacityPanel, { CapacitySummary } from "./StudyCapacityPanel";

vi.mock("../../api/study", () => ({
  getStudyCapacity: vi.fn(),
  setStudyDailyCapacity: vi.fn(),
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("shows unknown capacity without inventing an available limit", () => {
  render(<CapacitySummary days={[{
    date: "2026-11-19", candidate_minutes: 30, other_minutes: 20,
    total_minutes: 50, limit_minutes: null, verified: false, overloaded: false,
  }]} />);
  expect(screen.getByText(/上限未核实/)).toHaveTextContent("合计 50 分钟");
});

it("saves a user limit and rejects noninteger minutes", async () => {
  vi.mocked(getStudyCapacity).mockResolvedValue({ capacity: [{
    date: "2026-11-19", candidate_minutes: 30, other_minutes: 20,
    total_minutes: 50, limit_minutes: 90, verified: true, overloaded: false,
  }] });
  vi.mocked(setStudyDailyCapacity).mockResolvedValue({ saved: true });
  const plan = { id: "plan_capacity", updated_at: "2026-11-19T00:00:00Z" } as StudyPlan;
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}>
    <StudyCapacityPanel plan={plan} date="2026-11-19" />
  </QueryClientProvider>);
  fireEvent.click(screen.getByText("学习时间容量"));
  const input = await screen.findByDisplayValue("90");
  fireEvent.change(input, { target: { value: "120" } });
  fireEvent.click(screen.getByRole("button", { name: "保存学习上限" }));
  await waitFor(() => expect(setStudyDailyCapacity).toHaveBeenCalledWith("2026-11-19", 120));
  await screen.findByRole("status");
  fireEvent.change(input, { target: { value: "1.5" } });
  fireEvent.click(screen.getByRole("button", { name: "保存学习上限" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("整数分钟");
  expect(setStudyDailyCapacity).toHaveBeenCalledTimes(1);
});
