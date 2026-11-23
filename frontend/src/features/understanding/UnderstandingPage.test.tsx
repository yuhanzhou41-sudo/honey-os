import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import UnderstandingPage from "./UnderstandingPage";

vi.mock("../../api/understanding", () => ({
  fetchUnderstandingGraph: vi.fn().mockResolvedValue({
    total: 1,
    owner: "local-owner",
    labels: [
      {
        id: "ul_1",
        category_id: "behavior_pattern",
        scope_key: "workflow",
        canonical_key: "prefers_planning",
        text: "用户倾向先规划",
        state: "supported",
        grade: "medium",
        revision: 1,
        created_at: "2026-08-07",
        updated_at: "2026-08-07",
        suppressed: false,
        evidence: [
          {
            ref: "continuity:m1",
            relation: "support",
            occurred_at: "2026-08-07",
            source_revision: "2026-08-07",
            memory: {
              kind: "episode",
              created_at: "2026-08-07",
              content: "一起制定了计划",
              source_session_id: "s1",
              imprint: {
                status: "known",
                axis: "warmth",
                label: "温暖",
                formed_at: "2026-08-07",
              },
            },
          },
        ],
      },
    ],
  }),
  suppressUnderstandingLabel: vi.fn(),
  detachUnderstandingEvidence: vi.fn(),
}));

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <UnderstandingPage />
    </QueryClientProvider>,
  );
}

describe("UnderstandingPage", () => {
  it("shows the graph heading and renders real label data", async () => {
    renderPage();
    expect(await screen.findByText("Honey 对我的理解")).toBeInTheDocument();
    expect(await screen.findByText("用户倾向先规划")).toBeInTheDocument();
    // memory node hint shows the historical imprint label
    expect(await screen.findByText(/印象:温暖/)).toBeInTheDocument();
  });
});
