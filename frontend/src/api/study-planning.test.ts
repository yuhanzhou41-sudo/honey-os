import { afterEach, expect, it, vi } from "vitest";
import { requestJson } from "./client";
import { confirmManualStudyChange } from "./study-planning";

vi.mock("./client", () => ({
  requestJson: vi.fn(), apiPath: (path: string) => path,
  fetchWithLocalSessionRecovery: vi.fn(),
}));
afterEach(() => { vi.restoreAllMocks(); vi.clearAllMocks(); });
const preview = {
  plan: { title: "Preview", start_date: "2026-11-19", end_date: "2026-11-20", tasks: [] },
  expected_updated_at: "version-before",
};

it("confirms the same patch with its preview version", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.mocked(requestJson).mockResolvedValueOnce(preview).mockResolvedValueOnce({ plan: preview.plan });
  await confirmManualStudyChange("plan_test", { title: "Changed" }, "task_test");
  expect(requestJson).toHaveBeenLastCalledWith("/api/study/plans/plan_test/changes/confirm",
    expect.objectContaining({ body: JSON.stringify({
      patch: { title: "Changed" }, task_id: "task_test", expected_updated_at: "version-before",
    }) }));
});

it("does not write after cancellation", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  vi.mocked(requestJson).mockResolvedValueOnce(preview);
  await expect(confirmManualStudyChange("plan_test", { title: "Changed" })).rejects.toThrow("已取消");
  expect(requestJson).toHaveBeenCalledTimes(1);
});
