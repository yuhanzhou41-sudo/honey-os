import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useHoneyStore } from "../../runtime/honey-store";
import { MemoriesPage } from "./MemoriesPage";

const {
  fetchCompanionBootstrap,
  fetchUnderstanding,
  fetchUnderstandingDetail,
  updateUnderstanding,
  actOnUnderstanding,
} = vi.hoisted(() => ({
  fetchCompanionBootstrap: vi.fn(),
  fetchUnderstanding: vi.fn(),
  fetchUnderstandingDetail: vi.fn(),
  updateUnderstanding: vi.fn(),
  actOnUnderstanding: vi.fn(),
}));

vi.mock("../../api/companion", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/companion")>();
  return {
    ...actual,
    fetchCompanionBootstrap,
    fetchUnderstanding,
    fetchUnderstandingDetail,
    updateUnderstanding,
    actOnUnderstanding,
  };
});

const label = {
  id: "ul-1",
  category: "learning_work_style",
  scope_key: "learning",
  canonical_key: "mechanism-first",
  body: "似乎偏好先理解机制",
  state: "tentative",
  grade: "low" as const,
  revision: 2,
  created_at: "2026-11-20T00:00:00Z",
  updated_at: "2026-11-22T00:00:00Z",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoriesPage /></QueryClientProvider>);
}

async function openUnderstanding() {
  renderPage();
  fireEvent.click(screen.getByRole("button", { name: "Honey 的理解" }));
}

beforeEach(() => {
  vi.clearAllMocks();
  useHoneyStore.setState({ loading: false, error: null, memories: [], recentChapters: [] });
  fetchCompanionBootstrap.mockResolvedValue({
    profile: {},
    profile_details: {},
    session_id: "s1",
    session_key: "lane-a",
    messages: [],
    memories: [],
    recent_chapters: [],
    history: [],
    settings: { understanding_namespace: "general" },
  });
  fetchUnderstanding.mockResolvedValue({ items: [label], total: 1, limit: 50, offset: 0, policy_epoch: 4 });
  fetchUnderstandingDetail.mockResolvedValue({
    label,
    evidence: [
      {
        evidence_ref: "e1",
        event_group: "g1",
        relation: "support",
        source_revision: "r1",
        source_status: "recorded_unverified",
        // Defensive: the backend must not send source text, and the page must
        // never render it even if an upstream payload carries extra fields.
        evidence_quote: "原始消息正文不应出现",
      },
    ],
    versions: [],
  });
  updateUnderstanding.mockResolvedValue({ success: true, policy_epoch: 5, actor: "user_edit" });
  actOnUnderstanding.mockResolvedValue({ success: true, policy_epoch: 5, action: "suppress" });
});

afterEach(() => cleanup());

describe("Honey understanding management", () => {
  it("renders category, scope, grade, state and revision as a tentative view", async () => {
    await openUnderstanding();
    expect(await screen.findByText("似乎偏好先理解机制")).toBeInTheDocument();
    expect(screen.getByText("learning_work_style")).toBeInTheDocument();
    expect(screen.getByText("范围：learning")).toBeInTheDocument();
    expect(screen.getByText("证据等级：low")).toBeInTheDocument();
    expect(screen.getByText("状态：tentative")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText(/不是已确认的事实/)).toBeInTheDocument();
    expect(screen.getByText(/当前分区：general/)).toBeInTheDocument();
    expect(fetchUnderstanding).toHaveBeenCalledWith("lane-a", "general", 0);
  });

  it("marks unverified evidence as pending review and never shows raw source text", async () => {
    await openUnderstanding();
    await screen.findByText("似乎偏好先理解机制");
    fireEvent.click(screen.getByRole("button", { name: "来源与版本" }));
    expect(await screen.findByText(/当前有效性待来源复核/)).toBeInTheDocument();
    expect(screen.queryByText(/原始消息正文不应出现/)).not.toBeInTheDocument();
  });

  it("sends edit and suppression to the scoped backend instead of only changing local UI", async () => {
    await openUnderstanding();
    await screen.findByText("似乎偏好先理解机制");
    fireEvent.click(screen.getByRole("button", { name: "编辑/纠正" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "我更准确的表述" } });
    fireEvent.click(screen.getByRole("button", { name: "保存为用户编辑" }));
    await waitFor(() => expect(updateUnderstanding).toHaveBeenCalledWith("ul-1", "lane-a", "我更准确的表述", "general"));
    fireEvent.click(screen.getByRole("button", { name: "禁止使用" }));
    await waitFor(() => expect(actOnUnderstanding).toHaveBeenCalledWith("ul-1", "lane-a", "suppress", "general"));
  });

  it("shows a suppressed label without pretending its body is still known", async () => {
    fetchUnderstanding.mockResolvedValue({
      items: [{ ...label, body: "", state: "user_suppressed" }],
      total: 1,
      limit: 50,
      offset: 0,
      policy_epoch: 6,
    });
    actOnUnderstanding.mockResolvedValue({ success: true, policy_epoch: 7, action: "restore" });
    await openUnderstanding();
    expect(await screen.findByText("正文已因禁止或忘记而移除")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "编辑/纠正" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "恢复并重新评估" }));
    await waitFor(() => expect(actOnUnderstanding).toHaveBeenCalledWith("ul-1", "lane-a", "restore", "general"));
  });

  it("pages through more than fifty labels without changing partitions", async () => {
    fetchUnderstanding.mockImplementation((_lane: string, _namespace: string, offset: number) =>
      Promise.resolve({
        items: [{ ...label, id: `ul-${offset}`, body: offset === 0 ? "第一页理解" : "第二页理解" }],
        total: 120,
        limit: 50,
        offset,
        policy_epoch: 4,
      }));
    await openUnderstanding();
    expect(await screen.findByText("第一页理解")).toBeInTheDocument();
    expect(screen.getByText("第 1-1 条 / 共 120 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    expect(await screen.findByText("第二页理解")).toBeInTheDocument();
    await waitFor(() => expect(fetchUnderstanding).toHaveBeenCalledWith("lane-a", "general", 50));
    expect(screen.getByText("第 51-51 条 / 共 120 条")).toBeInTheDocument();
  });

  it("refuses to guess a partition when the gateway exposes no namespace", async () => {
    fetchCompanionBootstrap.mockResolvedValue({
      profile: {},
      profile_details: {},
      session_id: "s1",
      session_key: "lane-a",
      messages: [],
      memories: [],
      recent_chapters: [],
      history: [],
      settings: {},
    });
    await openUnderstanding();
    expect(await screen.findByText(/当前还没有配置可管理的理解分区/)).toBeInTheDocument();
    expect(fetchUnderstanding).not.toHaveBeenCalled();
  });

  it("renders an empty state instead of inventing labels", async () => {
    fetchUnderstanding.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0, policy_epoch: 0 });
    await openUnderstanding();
    expect(await screen.findByText("还没有形成可管理的理解")).toBeInTheDocument();
  });

  it("shows a bounded error state when the management API fails", async () => {
    fetchUnderstanding.mockRejectedValue(new Error("management api unavailable"));
    await openUnderstanding();
    expect(await screen.findByRole("alert")).toHaveTextContent("理解列表暂时没有加载成功");
  });
});
