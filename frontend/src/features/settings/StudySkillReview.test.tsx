import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { requestJson } from "../../api/client";
import { StudySkillReview } from "./StudySkillReview";

vi.mock("../../api/client", () => ({ requestJson: vi.fn() }));

afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("pins confirmation to the reviewed candidate and formats notes only after enablement", async () => {
  const candidate = {
    version: 1, digest: "fixture-digest", work_id: "fixture", approved: false,
    manifest: { name: "复习", purpose: "整理临床复习要点", heading: "笔记" },
    checks: ["合成样本按行整理"],
  };
  const request = vi.mocked(requestJson);
  request
    .mockResolvedValueOnce({ active_version: null, candidates: [candidate] })
    .mockResolvedValueOnce({ active_version: 1, candidates: [{ ...candidate, approved: true }] })
    .mockResolvedValueOnce({ note: "笔记\n\n• 查脉搏" });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <StudySkillReview />
    </QueryClientProvider>,
  );

  fireEvent.click(await screen.findByRole("button", { name: /^启用$/ }));
  expect(request).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("复习内容")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "确认启用 v1" }));
  const notes = await screen.findByLabelText("复习内容");
  expect(JSON.parse(String(request.mock.calls[1][1]?.body))).toEqual({
    action: "enable", version: 1, digest: "fixture-digest",
  });
  fireEvent.change(notes, { target: { value: "查脉搏" } });
  fireEvent.click(screen.getByRole("button", { name: "整理笔记" }));
  expect(await screen.findByRole("status")).toHaveTextContent("查脉搏");
});
