import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { listStudyResources, type StudyResource } from "../../api/study";
import { buildPlanningRequest, getStudyPlanningCapabilities } from "../../api/study-planning";
import PlanningRequestBuilder from "./PlanningRequestBuilder";

vi.mock("../../api/study", () => ({ listStudyResources: vi.fn() }));
vi.mock("../../api/study-planning", () => ({
  buildPlanningRequest: vi.fn(), getStudyPlanningCapabilities: vi.fn(),
  planAuthoringGuideUrl: () => "/guide", planTemplateUrl: () => "/template?version=1",
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

it("previews only explicitly selected material and clears stale output on edits", async () => {
  vi.mocked(getStudyPlanningCapabilities).mockResolvedValue({
    supported_schema_version: 2, supported_schema_versions: [1, 2],
  });
  vi.mocked(listStudyResources).mockResolvedValue({ resources: [
    { id: "resource_first", title: "Selected notes" } as StudyResource,
    { id: "resource_private", title: "Other notes" } as StudyResource,
  ] });
  vi.mocked(buildPlanningRequest).mockResolvedValue("# Planning Request\nSelected material");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><PlanningRequestBuilder /></QueryClientProvider>);
  expect(buildPlanningRequest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText("交给其他 AI 制定计划"));
  await screen.findByText(/当前支持 V2/);
  fireEvent.change(screen.getByLabelText("学习目标与考试范围"), { target: { value: "Biology exam" } });
  fireEvent.change(screen.getByLabelText("计划开始日期"), { target: { value: "2026-11-19" } });
  fireEvent.change(screen.getByLabelText("计划结束日期"), { target: { value: "2026-11-25" } });
  fireEvent.click(await screen.findByRole("checkbox", { name: "Selected notes" }));
  fireEvent.click(screen.getByRole("button", { name: "预览规划请求" }));
  await waitFor(() => expect(buildPlanningRequest).toHaveBeenCalledWith({
    objective: "Biology exam", start_date: "2026-11-19", end_date: "2026-11-25",
    constraints: "", resource_ids: ["resource_first"],
  }));
  expect(await screen.findByLabelText("规划请求预览")).toHaveValue("# Planning Request\nSelected material");
  expect(screen.getByRole("button", { name: "下载 planning_request.md" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("学习目标与考试范围"), { target: { value: "Changed exam" } });
  expect(screen.queryByLabelText("规划请求预览")).toBeNull();
  expect(buildPlanningRequest).toHaveBeenCalledTimes(1);
});
