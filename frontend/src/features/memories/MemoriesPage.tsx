import StudyGardenPanel from "../study/StudyGardenPanel";
import {
  ArrowCounterClockwiseIcon,
  BrainIcon,
  CheckIcon,
  ClockCounterClockwiseIcon,
  MagnifyingGlassIcon,
  PencilSimpleIcon,
  TrashIcon,
  XIcon,
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  deleteHistoricalMemory,
  fetchCompanionBootstrap,
  fetchHistoricalMemories,
  fetchHistoricalMemory,
  fetchHistoricalTrash,
  permanentlyDeleteHistoricalMemory,
  restoreHistoricalMemory,
  updateCompanionMemory,
  updateHistoricalMemory,
  type HistoricalMemoryDetail,
  type HistoricalMemoryItem,
  type MemoryItem,
  type RecentChapter,
} from "../../api/companion";
import { PageHeader } from "../../components/honey/PageHeader";
import { ErrorState, LoadingState } from "../../components/honey/PageState";
import { Button } from "../../components/ui/Button";
import { cn } from "../../lib/utils";
import { useHoneyStore } from "../../runtime/honey-store";

const filters = [
  { value: "all", label: "全部" },
  { value: "long_term_memory", label: "长期记忆" },
  { value: "recent_chapter", label: "最近" },
  { value: "commitment", label: "答应过的" },
  { value: "episode", label: "共同经历" },
  { value: "open_loop", label: "待续" },
];

const kindNames: Record<string, string> = {
  long_term_memory: "长期记忆",
  temporary_state: "最近状态",
  commitment: "答应过的",
  episode: "共同经历",
  open_loop: "待续",
};

function formatDate(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(date);
}

function memoryDate(memory: MemoryItem): string {
  return formatDate(memory.updated_at || memory.created_at);
}

function historicalDate(memory: HistoricalMemoryItem): string {
  return formatDate(memory.time_end || memory.occurred_at || memory.captured_at);
}

function companionMemoryCopy(memory: MemoryItem): string {
  const content = memory.content
    .replaceAll("用户", "你")
    .replaceAll("伴侣", "我")
    .replaceAll("你们", "我们")
    .trim();
  if (/^(我|我们|你)/.test(content)) return content;
  const lead: Record<string, string> = {
    long_term_memory: "我一直记得：",
    temporary_state: "我留意到你最近：",
    commitment: "我答应你的：",
    episode: "我记得我们一起：",
    open_loop: "我还想和你继续：",
  };
  return `${lead[memory.kind] || "我记得："}${content}`;
}

function SourceAvailability({ count = 0 }: { count?: number }) {
  if (!count) return null;
  return <span className="mt-2 w-fit rounded-md bg-amber-100 px-2 py-1 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-100">
    {count} 个原聊天已删除或不可用
  </span>;
}

export function MemoriesPage() {
  const queryClient = useQueryClient();
  const {
    loading,
    error,
    memories,
    recentChapters,
    replaceMemories,
    replaceRecentChapters,
    removeMemory,
  } = useHoneyStore();

  const [section, setSection] = useState<"mine" | "history" | "study">(() =>
    new URLSearchParams(window.location.search).get("section") === "study" ? "study" : "mine");
  const [historyView, setHistoryView] = useState<"library" | "trash">("library");
  const [filter, setFilter] = useState("all");
  const [partition, setPartition] = useState("all");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [notice, setNotice] = useState("");
  const [memoryEdit, setMemoryEdit] = useState<{ id: string; content: string } | null>(null);
  const pageSize = 30;

  const memoryRefresh = useQuery({
    queryKey: ["companion", "memories"],
    queryFn: () => fetchCompanionBootstrap(),
    enabled: section !== "study",
    refetchOnMount: "always",
    refetchInterval: section === "mine" ? 5_000 : false,
    staleTime: 0,
  });

  useEffect(() => {
    if (memoryRefresh.data?.memories) replaceMemories(memoryRefresh.data.memories);
    if (memoryRefresh.data?.recent_chapters) replaceRecentChapters(memoryRefresh.data.recent_chapters);
  }, [memoryRefresh.data, replaceMemories, replaceRecentChapters]);

  const history = useQuery({
    queryKey: ["memory-library", partition, search, offset],
    queryFn: () =>
      fetchHistoricalMemories({
        source: "deepseek",
        partition: partition === "all" ? undefined : partition,
        q: search || undefined,
        limit: pageSize,
        offset,
      }),
    enabled: section === "history" && historyView === "library",
    staleTime: 15_000,
  });

  const trash = useQuery({
    queryKey: ["memory-trash", offset],
    queryFn: () => fetchHistoricalTrash({ limit: pageSize, offset }),
    enabled: section === "history" && historyView === "trash",
    staleTime: 5_000,
  });

  const detail = useQuery({
    queryKey: ["memory-detail", selectedId],
    queryFn: () => fetchHistoricalMemory(selectedId!),
    enabled: Boolean(selectedId),
    staleTime: 0,
  });

  useEffect(() => {
    if (detail.data?.item && !editing) {
      setDraft(detail.data.item.summary);
    }
  }, [detail.data, editing]);

  const legacyMutation = useMutation({
    mutationFn: ({ memory, action }: { memory: MemoryItem; action: "resolve" | "forget" }) =>
      updateCompanionMemory(memory.id, action),
    onSuccess: (data) => {
      removeMemory(data.id);
      setNotice(data.action === "resolve" ? "已经标记为完成" : "这件事已经忘记了");
    },
    onError: () => setNotice("刚才没有改成功，请再试一次"),
  });

  const editNativeMemory = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) => updateCompanionMemory(id, "edit", content),
    onSuccess: async () => {
      setMemoryEdit(null);
      setNotice("已保存记忆");
      await queryClient.invalidateQueries({ queryKey: ["companion", "memories"] });
    },
    onError: () => setNotice("刚才没有保存，请再试一次"),
  });

  const editMutation = useMutation({
    mutationFn: ({ id, summary }: { id: string; summary: string }) =>
      updateHistoricalMemory(id, summary),
    onSuccess: async (data) => {
      setEditing(false);
      setDraft(data.item.summary);
      setNotice("已经保存修改，旧版本仍保留在修改记录里");
      await queryClient.invalidateQueries({ queryKey: ["memory-library"] });
      await queryClient.invalidateQueries({ queryKey: ["memory-detail", data.item.id] });
    },
    onError: () => setNotice("修改没有保存成功，请再试一次"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteHistoricalMemory(id),
    onSuccess: async () => {
      setSelectedId(null);
      setEditing(false);
      setNotice("已移入回收箱，可以随时恢复");
      await queryClient.invalidateQueries({ queryKey: ["memory-library"] });
      await queryClient.invalidateQueries({ queryKey: ["memory-trash"] });
    },
    onError: () => setNotice("没有成功移入回收箱，请再试一次"),
  });

  const restoreMutation = useMutation({
    mutationFn: (id: string) => restoreHistoricalMemory(id),
    onSuccess: async () => {
      setSelectedId(null);
      setNotice("记忆已经恢复");
      await queryClient.invalidateQueries({ queryKey: ["memory-library"] });
      await queryClient.invalidateQueries({ queryKey: ["memory-trash"] });
    },
    onError: () => setNotice("恢复失败，请再试一次"),
  });

  const permanentDeleteMutation = useMutation({
    mutationFn: (id: string) => permanentlyDeleteHistoricalMemory(id),
    onSuccess: async () => {
      setSelectedId(null);
      setNotice("这条历史记忆已永久删除，无法恢复");
      await queryClient.invalidateQueries({ queryKey: ["memory-library"] });
      await queryClient.invalidateQueries({ queryKey: ["memory-trash"] });
    },
    onError: () => setNotice("永久删除失败，请再试一次"),
  });

  const visible = useMemo(
    () => (filter === "all" ? memories : memories.filter((memory) => memory.kind === filter)),
    [filter, memories],
  );
  const visibleChapters =
    filter === "all" || filter === "recent_chapter" ? recentChapters : [];

  const sectionTabs = <div className="mt-6 grid grid-cols-3 gap-2 rounded-[var(--radius-lg)] bg-[var(--surface)] p-1">
    <SectionButton active={section === "mine"} onClick={() => setSection("mine")}>我的记忆</SectionButton>
    <SectionButton active={section === "history"} onClick={() => setSection("history")}>历史记忆</SectionButton>
    <SectionButton active={section === "study"} onClick={() => setSection("study")}>学习花园与记忆</SectionButton>
  </div>;
  if (section === "study") return <PageFrame><PageHeader title="记忆" description="学习的每一步，都留在自己的花园里。" />{sectionTabs}<StudyGardenPanel standalone /></PageFrame>;
  if (loading) return <PageFrame><PageHeader title="记忆" description="日常记忆与学习花园在这里分别查看。" />{sectionTabs}<LoadingState /></PageFrame>;
  if (error) return <PageFrame><PageHeader title="记忆" description="日常记忆与学习花园在这里分别查看。" />{sectionTabs}<ErrorState /></PageFrame>;

  const currentPage = historyView === "library" ? history.data : trash.data;
  const currentLoading = historyView === "library" ? history.isLoading : trash.isLoading;
  const currentError = historyView === "library" ? history.isError : trash.isError;

  return (
    <PageFrame>
      <PageHeader
        title="记忆"
        description="正在形成的记忆和从过去带来的历史，会分开保存在这里。"
      />

      {sectionTabs}

      {notice ? (
        <p className="mt-3 text-sm text-[var(--foreground-muted)]" role="status">
          {notice}
        </p>
      ) : null}

      {section === "mine" ? (
        <>
          <div className="mt-6 flex gap-2 overflow-x-auto pb-2">
            {filters.map((item) => (
              <HistoryChip
                key={item.value}
                selected={filter === item.value}
                onClick={() => setFilter(item.value)}
              >
                {item.label}
              </HistoryChip>
            ))}
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {visibleChapters.map((chapter: RecentChapter) => (
              <article
                key={`recent-${chapter.id}`}
                className="flex min-h-48 flex-col rounded-[var(--radius-lg)] bg-[var(--surface)] p-5"
              >
                <header className="flex items-center justify-between gap-3 text-xs text-[var(--foreground-faint)]">
                  <span className="flex items-center gap-2">
                    <BrainIcon size={17} className="text-[var(--accent)]" />
                    最近想起
                  </span>
                  <span>
                    {memoryDate({
                      id: chapter.id,
                      kind: "recent_chapter",
                      content: chapter.summary,
                      status: "active",
                      created_at: chapter.created_at,
                    })}
                  </span>
                </header>
                <h2 className="mt-5 font-semibold leading-6">{chapter.title}</h2>
                <SourceAvailability count={chapter.unavailable_source_count} />
                <p className="mt-2 break-words text-[15px] leading-7 text-[var(--foreground-muted)]">
                  {chapter.summary}
                </p>
              </article>
            ))}

            {visible.length ? (
              visible.map((memory) => (
                <article
                  key={memory.id}
                  className="flex min-h-48 flex-col rounded-[var(--radius-lg)] bg-[var(--surface)] p-5"
                >
                  <header className="flex items-center justify-between gap-3 text-xs text-[var(--foreground-faint)]">
                    <span className="flex items-center gap-2">
                      <BrainIcon size={17} className="text-[var(--accent)]" />
                      {kindNames[memory.kind] || memory.kind}
                    </span>
                    <span>{memoryDate(memory)}</span>
                  </header>
                  <SourceAvailability count={memory.unavailable_source_count} />
                  {memoryEdit?.id === memory.id ? (
                    <div className="mt-4 grid gap-2">
                      <textarea aria-label="记忆内容" maxLength={500} value={memoryEdit.content}
                        onChange={(event) => setMemoryEdit({ id: memory.id, content: event.target.value })}
                        className="rounded border border-[var(--border)] bg-[var(--surface-raised)] p-2" />
                      <div className="flex gap-2">
                        <Button type="button" disabled={!memoryEdit.content.trim() || editNativeMemory.isPending}
                          onClick={() => editNativeMemory.mutate(memoryEdit)}>保存</Button>
                        <Button type="button" variant="ghost" disabled={editNativeMemory.isPending}
                          onClick={() => setMemoryEdit(null)}>取消</Button>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-5 break-words text-[15px] leading-7">{companionMemoryCopy(memory)}</p>
                  )}
                  <div className="mt-auto flex flex-wrap gap-2 pt-5">
                    {memory.can_edit && memoryEdit?.id !== memory.id ? (
                      <Button type="button" variant="ghost" disabled={editNativeMemory.isPending}
                        onClick={() => setMemoryEdit({ id: memory.id, content: memory.content })}>编辑</Button>
                    ) : null}
                    {memory.kind === "open_loop" || memory.kind === "commitment" ? (
                      <Button
                        type="button"
                        variant="secondary"
                        disabled={legacyMutation.isPending}
                        onClick={() => legacyMutation.mutate({ memory, action: "resolve" })}
                      >
                        <CheckIcon size={16} />
                        已经完成
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={legacyMutation.isPending}
                      onClick={() => legacyMutation.mutate({ memory, action: "forget" })}
                    >
                      <TrashIcon size={16} />
                      忘记
                    </Button>
                  </div>
                </article>
              ))
            ) : visibleChapters.length ? null : (
              <EmptyState
                title="这一类暂时是空的"
                body="继续自然地聊天就好，值得留下的内容会慢慢出现在这里。"
              />
            )}
          </div>
        </>
      ) : (
        <>
          <div className="mt-6 flex gap-2">
            <HistoryChip
              selected={historyView === "library"}
              onClick={() => {
                setHistoryView("library");
                setOffset(0);
                setSelectedId(null);
              }}
            >
              历史记忆
            </HistoryChip>
            <HistoryChip
              selected={historyView === "trash"}
              onClick={() => {
                setHistoryView("trash");
                setOffset(0);
                setSelectedId(null);
              }}
            >
              <span className="inline-flex items-center gap-1">
                <TrashIcon size={14} />
                回收箱
              </span>
            </HistoryChip>
          </div>

          {historyView === "library" ? (
            <>
              <div className="mt-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-4">
                <div className="flex items-start gap-3">
                  <ClockCounterClockwiseIcon
                    size={22}
                    className="mt-0.5 shrink-0 text-[var(--accent)]"
                  />
                  <div>
                    <h2 className="font-semibold">从过去带来的记忆</h2>
                    <p className="mt-1 text-sm leading-6 text-[var(--foreground-muted)]">
                      历史导入会保留来源和时间。你可以修正整理后的文字，修改记录不会丢失；删除后先进入回收箱。
                    </p>
                  </div>
                </div>
              </div>

              <form
                className="mt-4 flex gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  setSearch(query.trim());
                  setOffset(0);
                }}
              >
                <div className="flex min-h-10 flex-1 items-center gap-2 rounded-full bg-[var(--surface)] px-4">
                  <MagnifyingGlassIcon
                    size={16}
                    className="text-[var(--foreground-faint)]"
                  />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索历史记忆"
                    className="min-w-0 flex-1 bg-transparent text-sm outline-none"
                  />
                </div>
                <Button type="submit" variant="secondary">搜索</Button>
              </form>
            </>
          ) : (
            <div className="mt-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-4">
              <h2 className="font-semibold">回收箱</h2>
              <p className="mt-1 text-sm leading-6 text-[var(--foreground-muted)]">
                这里的记忆已经被明确停用，不会参与之后的记忆检索。当前阶段可以恢复；永久删除会在下一阶段加入二次确认。
              </p>
            </div>
          )}

          {currentLoading ? <div className="mt-8"><LoadingState /></div> : null}
          {currentError ? <div className="mt-8"><ErrorState /></div> : null}

          {currentPage ? (
            <>
              {historyView === "library" ? (
                <div className="mt-4 flex gap-2 overflow-x-auto pb-2">
                  <HistoryChip
                    selected={partition === "all"}
                    onClick={() => {
                      setPartition("all");
                      setOffset(0);
                    }}
                  >
                    全部分区
                  </HistoryChip>
                  {currentPage.partitions.map((item) => (
                    <HistoryChip
                      key={item.key}
                      selected={partition === item.key}
                      onClick={() => {
                        setPartition(item.key);
                        setOffset(0);
                      }}
                    >
                      {item.label} · {item.count}
                    </HistoryChip>
                  ))}
                </div>
              ) : null}

              <div className="mt-3 flex items-center justify-between text-xs text-[var(--foreground-faint)]">
                <span>共 {currentPage.total} 条</span>
                <span>
                  {historyView === "trash"
                    ? "已停用的历史记忆"
                    : "DeepSeek 历史 · 按时间从新到旧"}
                </span>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {currentPage.items.length ? (
                  currentPage.items.map((memory) => (
                    <button
                      key={memory.id}
                      type="button"
                      onClick={() => setSelectedId(memory.id)}
                      className="flex min-h-52 flex-col rounded-[var(--radius-lg)] bg-[var(--surface)] p-5 text-left transition hover:-translate-y-0.5 hover:bg-[var(--surface-raised)]"
                    >
                      <header className="flex w-full items-center justify-between gap-3 text-xs text-[var(--foreground-faint)]">
                        <span className="flex items-center gap-2">
                          <ClockCounterClockwiseIcon
                            size={17}
                            className="text-[var(--accent)]"
                          />
                          {memory.partition_label}
                        </span>
                        <span>
                          {historyView === "trash"
                            ? formatDate(memory.deleted_at)
                            : historicalDate(memory)}
                        </span>
                      </header>
                      <p className="mt-4 break-words text-[15px] leading-7">
                        {memory.summary}
                      </p>
                      <div className="mt-auto flex flex-wrap gap-x-3 gap-y-1 pt-5 text-xs text-[var(--foreground-faint)]">
                        <span>DeepSeek 历史</span>
                        <span>{memory.provenance_count} 条原始证据</span>
                        {historyView === "trash" ? <span>已移入回收箱</span> : null}
                      </div>
                    </button>
                  ))
                ) : (
                  <EmptyState
                    title={
                      historyView === "trash"
                        ? "回收箱是空的"
                        : "这个分区暂时没有匹配的历史记忆"
                    }
                    body={
                      historyView === "trash"
                        ? "删除的历史记忆会先出现在这里。"
                        : "可以切换分区，或者换一个搜索词。"
                    }
                  />
                )}
              </div>

              {currentPage.total > pageSize ? (
                <div className="mt-6 flex items-center justify-center gap-3">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - pageSize))}
                  >
                    上一页
                  </Button>
                  <span className="text-sm text-[var(--foreground-muted)]">
                    {Math.floor(offset / pageSize) + 1} /{" "}
                    {Math.ceil(currentPage.total / pageSize)}
                  </span>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={offset + pageSize >= currentPage.total}
                    onClick={() => setOffset(offset + pageSize)}
                  >
                    下一页
                  </Button>
                </div>
              ) : null}
            </>
          ) : null}
        </>
      )}

      {selectedId ? (
        <MemoryDetailDialog
          loading={detail.isLoading}
          item={detail.data?.item}
          editing={editing}
          draft={draft}
          setDraft={setDraft}
          setEditing={setEditing}
          close={() => {
            setSelectedId(null);
            setEditing(false);
          }}
          save={() =>
            editMutation.mutate({ id: selectedId, summary: draft.trim() })
          }
          remove={() => deleteMutation.mutate(selectedId)}
          restore={() => restoreMutation.mutate(selectedId)}
          permanentlyDelete={() => permanentDeleteMutation.mutate(selectedId)}
          pending={
            editMutation.isPending ||
            deleteMutation.isPending ||
            restoreMutation.isPending ||
            permanentDeleteMutation.isPending
          }
        />
      ) : null}
    </PageFrame>
  );
}

function MemoryDetailDialog({
  loading,
  item,
  editing,
  draft,
  setDraft,
  setEditing,
  close,
  save,
  remove,
  restore,
  permanentlyDelete,
  pending,
}: {
  loading: boolean;
  item?: HistoricalMemoryDetail;
  editing: boolean;
  draft: string;
  setDraft: (value: string) => void;
  setEditing: (value: boolean) => void;
  close: () => void;
  save: () => void;
  remove: () => void;
  restore: () => void;
  permanentlyDelete: () => void;
  pending: boolean;
}) {
  const inTrash = item?.status === "user_suppressed";
  const [confirmPermanentDelete, setConfirmPermanentDelete] = useState(false);

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/35 p-0 sm:items-center sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="历史记忆详情"
    >
      <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-t-[var(--radius-lg)] bg-[var(--background)] p-5 shadow-xl sm:rounded-[var(--radius-lg)] sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs text-[var(--foreground-faint)]">
              {inTrash ? "回收箱" : item?.partition_label || "历史记忆"}
            </p>
            <h2 className="mt-1 text-xl font-semibold">记忆详情</h2>
          </div>
          <button
            type="button"
            onClick={close}
            className="rounded-full p-2 text-[var(--foreground-muted)] hover:bg-[var(--surface)]"
          >
            <XIcon size={20} />
          </button>
        </div>

        {loading || !item ? (
          <div className="py-10"><LoadingState /></div>
        ) : (
          <>
            {editing ? (
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                rows={9}
                className="mt-5 w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] p-4 text-[15px] leading-7 outline-none focus:ring-2 focus:ring-[var(--focus)]"
              />
            ) : (
              <p className="mt-5 whitespace-pre-wrap break-words text-[15px] leading-7">
                {item.summary}
              </p>
            )}

            <dl className="mt-6 grid gap-3 rounded-[var(--radius-md)] bg-[var(--surface)] p-4 text-sm sm:grid-cols-2">
              <Meta
                label="来源"
                value={
                  item.source_system === "deepseek"
                    ? "DeepSeek 历史导入"
                    : item.source_system
                }
              />
              <Meta label="分区" value={item.partition_label} />
              <Meta
                label="代表时间"
                value={formatDate(item.time_end || item.occurred_at)}
              />
              <Meta label="原始证据" value={`${item.provenance.length} 条`} />
              {item.time_start &&
              item.time_end &&
              item.time_start !== item.time_end ? (
                <Meta
                  label="时间跨度"
                  value={`${formatDate(item.time_start)} → ${formatDate(
                    item.time_end,
                  )}`}
                />
              ) : null}
              {item.trash?.active ? (
                <Meta
                  label="移入回收箱"
                  value={formatDate(item.trash.deleted_at)}
                />
              ) : null}
            </dl>

            {item.revisions.length ? (
              <details className="mt-4 rounded-[var(--radius-md)] border border-[var(--border)] p-4">
                <summary className="cursor-pointer text-sm font-medium">
                  修改记录 ·{" "}
                  {
                    item.revisions.filter(
                      (revision) => revision.event_type === "user_edit",
                    ).length
                  }
                </summary>
                <div className="mt-3 space-y-4">
                  {item.revisions.map((revision) => (
                    <div
                      key={revision.id}
                      className="border-t border-[var(--border)] pt-3 text-sm"
                    >
                      <p className="text-xs text-[var(--foreground-faint)]">
                        {revision.event_type === "user_edit"
                          ? "手动编辑"
                          : "从回收箱恢复"}{" "}
                        · {formatDate(revision.created_at)}
                      </p>
                      {revision.payload.old_summary ? (
                        <p className="mt-2 text-[var(--foreground-muted)]">
                          原内容：{revision.payload.old_summary}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </details>
            ) : null}

            <details className="mt-4 rounded-[var(--radius-md)] border border-[var(--border)] p-4">
              <summary className="cursor-pointer text-sm font-medium">
                查看原始证据 · {item.provenance.length}
              </summary>
              <div className="mt-3 space-y-3">
                {item.provenance.map((evidence) => (
                  <blockquote
                    key={evidence.id}
                    className="rounded-[var(--radius-md)] bg-[var(--surface)] p-3 text-sm leading-6 text-[var(--foreground-muted)]"
                  >
                    {evidence.evidence_quote || "（无可显示正文）"}
                  </blockquote>
                ))}
              </div>
            </details>

            <div className="mt-6 flex flex-wrap gap-2">
              {inTrash ? (
                <>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={pending}
                    onClick={restore}
                  >
                    <ArrowCounterClockwiseIcon size={16} />
                    恢复
                  </Button>
                  {!confirmPermanentDelete ? (
                    <Button
                      type="button"
                      variant="ghost"
                      disabled={pending}
                      onClick={() => setConfirmPermanentDelete(true)}
                    >
                      <TrashIcon size={16} />
                      永久删除
                    </Button>
                  ) : (
                    <div className="w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] p-4">
                      <p className="text-sm font-medium">确认永久删除？</p>
                      <p className="mt-1 text-sm leading-6 text-[var(--foreground-muted)]">
                        记忆正文、原始证据和修改记录都会被删除，之后无法恢复。系统只保留最小来源阻止标记，防止同一条历史记录再次被导入复活。
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="secondary"
                          disabled={pending}
                          onClick={permanentlyDelete}
                        >
                          确认永久删除
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          disabled={pending}
                          onClick={() => setConfirmPermanentDelete(false)}
                        >
                          取消
                        </Button>
                      </div>
                    </div>
                  )}
                </>
              ) : editing ? (
                <>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={pending || !draft.trim()}
                    onClick={save}
                  >
                    保存修改
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={pending}
                    onClick={() => {
                      setDraft(item.summary);
                      setEditing(false);
                    }}
                  >
                    取消
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={pending}
                    onClick={() => setEditing(true)}
                  >
                    <PencilSimpleIcon size={16} />
                    编辑
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={pending}
                    onClick={remove}
                  >
                    <TrashIcon size={16} />
                    移入回收箱
                  </Button>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-[var(--foreground-faint)]">{label}</dt>
      <dd className="mt-1">{value}</dd>
    </div>
  );
}

function SectionButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "min-h-11 rounded-[calc(var(--radius-lg)-4px)] px-4 text-sm font-medium transition-colors",
        active
          ? "bg-[var(--foreground)] text-[var(--background)]"
          : "text-[var(--foreground-muted)] hover:text-[var(--foreground)]",
      )}
    >
      {children}
    </button>
  );
}

function HistoryChip({
  selected,
  onClick,
  children,
}: {
  selected: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "min-h-9 shrink-0 rounded-full px-3 text-xs transition-colors",
        selected
          ? "bg-[var(--foreground)] text-[var(--background)]"
          : "bg-[var(--surface)] text-[var(--foreground-muted)] hover:text-[var(--foreground)]",
      )}
    >
      {children}
    </button>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] p-8 sm:col-span-2">
      <h2 className="font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-[var(--foreground-muted)]">
        {body}
      </p>
    </div>
  );
}

function PageFrame({ children }: { children: React.ReactNode }) {
  return (
    <section className="mx-auto w-full max-w-5xl px-5 py-7 sm:px-9 sm:py-10">
      {children}
    </section>
  );
}
