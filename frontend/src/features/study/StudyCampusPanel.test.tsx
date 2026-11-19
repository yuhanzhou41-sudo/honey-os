import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { StudyCampusPanel } from "./StudyCampusPanel";

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

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

it("shows upcoming active Study tasks", async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <StudyCampusPanel />
    </QueryClientProvider>,
  );

  expect(await screen.findByText("准备复习")).toBeInTheDocument();
  expect(screen.queryByText("已结束任务")).not.toBeInTheDocument();
});
