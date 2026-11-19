import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { StudyPlan } from "../../api/study";
import { confirmChatStudyPlan, previewChatStudyPlan, type PlanningPreview } from "../../api/study-planning";
import StudyPlanDraft from "./StudyPlanDraft";

vi.mock("../../api/study-planning", () => ({
  previewChatStudyPlan: vi.fn(), confirmChatStudyPlan: vi.fn(),
}));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

const preview: PlanningPreview = {
  plan: {
    id: "plan_preview", title: "First proposal", start_date: "2026-11-19",
    end_date: "2026-11-20", tasks: [], schema_version: 2,
  } as unknown as StudyPlan,
  expected_updated_at: null,
};

it("requires a fresh preview when draft content changes", async () => {
  vi.mocked(previewChatStudyPlan).mockResolvedValue(preview);
  const { rerender } = render(<StudyPlanDraft draft={{ markdown: "first", revision: false }} />);
  fireEvent.click(screen.getByRole("button", { name: "预览学习计划" }));
  await screen.findByRole("button", { name: "确认保存到学习" });
  rerender(<StudyPlanDraft draft={{ markdown: "second", revision: false }} />);
  expect(screen.queryByRole("button", { name: "确认保存到学习" })).toBeNull();
  expect(confirmChatStudyPlan).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "预览学习计划" }));
  await waitFor(() => expect(previewChatStudyPlan).toHaveBeenLastCalledWith({
    markdown: "second", revision: false,
  }));
});

it("ignores preview results for an earlier draft", async () => {
  let resolve!: (value: PlanningPreview) => void;
  vi.mocked(previewChatStudyPlan).mockReturnValue(new Promise(result => { resolve = result; }));
  const { rerender } = render(<StudyPlanDraft draft={{ markdown: "first", revision: false }} />);
  fireEvent.click(screen.getByRole("button", { name: "预览学习计划" }));
  rerender(<StudyPlanDraft draft={{ markdown: "second", revision: false }} />);
  await act(async () => { resolve(preview); });
  expect(screen.queryByText(/First proposal/)).toBeNull();
  expect(screen.getByRole("button", { name: "预览学习计划" })).toBeEnabled();
  expect(confirmChatStudyPlan).not.toHaveBeenCalled();
});
