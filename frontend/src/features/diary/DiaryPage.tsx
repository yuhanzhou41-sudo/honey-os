import { ArrowClockwiseIcon, BookOpenTextIcon, CheckIcon, PencilSimpleIcon, PlusIcon, TrashIcon, XIcon } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import {
  createCompanionDiaryEntry,
  deleteCompanionDiaryEntry,
  fetchCompanionDiary,
  permanentlyDeleteCompanionDiaryEntry,
  retryCompanionDiary,
  restoreCompanionDiaryEntry,
  updateCompanionDiaryEntry,
  type DiaryEntry,
} from "../../api/companion";
import { PageHeader } from "../../components/honey/PageHeader";
import { ErrorState, LoadingState } from "../../components/honey/PageState";
import { Button } from "../../components/ui/Button";
import { useHoneyStore } from "../../runtime/honey-store";

const diaryKey = ["companion", "diary"] as const;

function localDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function displayDate(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(date);
}

function displayDateTime(value: string | null | undefined): string {
  if (!value) return "尚无记录";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN");
}

export function DiaryPage() {
  const companionName = useHoneyStore((state) => state.name);
  const queryClient = useQueryClient();
  const [composing, setComposing] = useState(false);
  const [entryDate, setEntryDate] = useState(localDate);
  const [draft, setDraft] = useState("");
  const [allowAiView, setAllowAiView] = useState(true);
  const [allowMemory, setAllowMemory] = useState(false);
  const [editingId, setEditingId] = useState("");
  const [editingContent, setEditingContent] = useState("");
  const [notice, setNotice] = useState("");
  const [showTrash, setShowTrash] = useState(false);

  const diary = useQuery({
    queryKey: diaryKey,
    queryFn: fetchCompanionDiary,
    refetchInterval: (query) => query.state.data?.automation.status === "pending" ? 3000 : false,
  });
  const entries = diary.data?.entries ?? [];
  const trash = diary.data?.trash ?? [];
  const groups = useMemo(() => {
    const result = new Map<string, DiaryEntry[]>();
    for (const entry of entries) {
      const current = result.get(entry.entry_date) ?? [];
      current.push(entry);
      result.set(entry.entry_date, current);
    }
    return [...result.entries()];
  }, [entries]);

  const createEntry = useMutation({
    mutationFn: createCompanionDiaryEntry,
    onSuccess: async () => {
      setDraft("");
      setComposing(false);
      setNotice("日记已经保存");
      await queryClient.invalidateQueries({ queryKey: diaryKey });
    },
    onError: () => setNotice("刚才没有保存成功，请再试一次"),
  });
  const updateEntry = useMutation({
    mutationFn: ({ id, changes }: {
      id: string;
      changes: Partial<Pick<DiaryEntry, "content" | "allow_ai_view" | "allow_memory">>;
    }) => updateCompanionDiaryEntry(id, changes),
    onSuccess: async () => {
      setEditingId("");
      setEditingContent("");
      setNotice("修改已经保存");
      await queryClient.invalidateQueries({ queryKey: diaryKey });
    },
    onError: () => setNotice("刚才没有修改成功，请再试一次"),
  });
  const deleteEntry = useMutation({
    mutationFn: deleteCompanionDiaryEntry,
    onSuccess: async () => {
      setNotice("这篇日记已经删除");
      await queryClient.invalidateQueries({ queryKey: diaryKey });
    },
    onError: () => setNotice("刚才没有删除成功，请再试一次"),
  });
  const retryGeneration = useMutation({
    mutationFn: retryCompanionDiary,
    onSuccess: async () => {
      setNotice("已经安排重新生成，页面会自动更新");
      await queryClient.invalidateQueries({ queryKey: diaryKey });
    },
    onError: () => setNotice("重新生成没有启动成功，请稍后再试"),
  });
  const restoreEntry = useMutation({
    mutationFn: restoreCompanionDiaryEntry,
    onSuccess: async () => {
      setNotice("日记已经恢复");
      await queryClient.invalidateQueries({ queryKey: diaryKey });
    },
    onError: () => setNotice("恢复失败，请再试一次"),
  });
  const permanentlyDeleteEntry = useMutation({
    mutationFn: permanentlyDeleteCompanionDiaryEntry,
    onSuccess: async () => {
      setNotice("日记已经永久删除");
      await queryClient.invalidateQueries({ queryKey: diaryKey });
    },
    onError: () => setNotice("永久删除失败，请再试一次"),
  });

  function submitNew(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content) return;
    setNotice("");
    createEntry.mutate({
      entry_date: entryDate,
      content,
      allow_ai_view: allowAiView || allowMemory,
      allow_memory: allowMemory,
    });
  }

  if (diary.isLoading) return <PageFrame><LoadingState /></PageFrame>;
  if (diary.isError) return <PageFrame><ErrorState /></PageFrame>;

  return (
    <PageFrame>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PageHeader title="共同日记" description={`你和${companionName}写下的日常，会按日期一起留在这里。`} />
        <div className="flex gap-2">
          <Button type="button" variant="secondary" onClick={() => setShowTrash((value) => !value)}>
            <TrashIcon size={17} />回收箱{trash.length ? ` (${trash.length})` : ""}
          </Button>
          <Button type="button" onClick={() => setComposing(true)} disabled={composing}>
            <PlusIcon size={17} />写一篇
          </Button>
        </div>
      </div>

      {notice ? <p className="mt-4 text-sm text-[var(--foreground-muted)]" role="status">{notice}</p> : null}

      {diary.data?.automation ? (
        <section className="mt-5 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4" aria-label="晚间日记运行状态">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">晚间日记</h2>
              <p className="mt-1 text-sm text-[var(--foreground-muted)]">
                {diary.data.automation.status === "completed" ? "已经生成" :
                  diary.data.automation.status === "pending" ? "正在生成" :
                    diary.data.automation.status === "failed" ? "生成失败" : "等待生成"}
                {` · 目标日期 ${diary.data.automation.entry_date}`}
              </p>
            </div>
            {diary.data.automation.status === "failed" ? (
              <Button
                type="button"
                variant="secondary"
                disabled={retryGeneration.isPending}
                onClick={() => retryGeneration.mutate(diary.data!.automation.entry_date)}
              >
                <ArrowClockwiseIcon size={16} />重新生成
              </Button>
            ) : null}
          </div>
          <div className="mt-3 grid gap-2 text-xs text-[var(--foreground-muted)] sm:grid-cols-3">
            <span>开始：{displayDateTime(diary.data.automation.started_at)}</span>
            <span>完成：{displayDateTime(diary.data.automation.completed_at)}</span>
            <span>读取用户日记：{diary.data.automation.user_read_count} 篇</span>
            <span>下次计划：{displayDateTime(diary.data.automation.next_generation_at)}</span>
            <span>待整理日记：{diary.data.memory_progress.diary_dates} 天，{diary.data.memory_progress.diary_units} 单位</span>
            <span>共享触发阈值：{diary.data.memory_progress.trigger_units} 单位</span>
          </div>
          {diary.data.automation.error ? (
            <p className="mt-3 rounded-[var(--radius-md)] bg-[var(--surface)] p-3 text-xs text-[var(--danger,#b42318)]" role="alert">
              {diary.data.automation.error}
            </p>
          ) : null}
        </section>
      ) : null}

      {showTrash ? (
        <section className="mt-5 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4" aria-label="日记回收箱">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="font-semibold">回收箱</h2>
              <p className="mt-1 text-sm text-[var(--foreground-muted)]">
                删除的用户日记保留 {diary.data?.trash_retention_days ?? 30} 天，期间不会被 AI 查看或用于记忆整理。
              </p>
            </div>
            <Button type="button" size="icon" variant="ghost" aria-label="关闭回收箱" onClick={() => setShowTrash(false)}>
              <XIcon size={18} />
            </Button>
          </div>
          <div className="mt-4 space-y-3">
            {trash.map((entry) => (
              <article key={entry.id} className="rounded-[var(--radius-md)] bg-[var(--surface)] p-4">
                <p className="text-xs text-[var(--foreground-faint)]">{displayDate(entry.entry_date)} · 删除于 {displayDateTime(entry.deleted_at)}</p>
                <p className="mt-2 line-clamp-4 whitespace-pre-wrap break-words text-sm leading-6">{entry.content}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button type="button" variant="secondary" disabled={restoreEntry.isPending} onClick={() => restoreEntry.mutate(entry.id)}>
                    <ArrowClockwiseIcon size={16} />恢复
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={permanentlyDeleteEntry.isPending}
                    onClick={() => {
                      if (window.confirm("永久删除后无法恢复，确定继续吗？")) permanentlyDeleteEntry.mutate(entry.id);
                    }}
                  >
                    <TrashIcon size={16} />永久删除
                  </Button>
                </div>
              </article>
            ))}
            {!trash.length ? <p className="text-sm text-[var(--foreground-muted)]">回收箱是空的。</p> : null}
          </div>
        </section>
      ) : null}

      {composing ? (
        <form className="mt-6 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-5" onSubmit={submitNew}>
          <div className="flex items-center justify-between gap-3">
            <label className="text-sm font-medium" htmlFor="diary-date">日记日期</label>
            <Button type="button" size="icon" variant="ghost" aria-label="取消新建" onClick={() => { setComposing(false); setDraft(""); }}>
              <XIcon size={18} />
            </Button>
          </div>
          <input id="diary-date" type="date" value={entryDate} onChange={(event) => setEntryDate(event.target.value)} className="mt-3 min-h-11 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 text-sm outline-none focus:ring-2 focus:ring-[var(--focus)]" />
          <textarea autoFocus value={draft} maxLength={20_000} rows={7} onChange={(event) => setDraft(event.target.value)} placeholder="今天发生了什么？" className="mt-3 w-full resize-y rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] p-4 text-[15px] leading-7 outline-none placeholder:text-[var(--foreground-faint)] focus:ring-2 focus:ring-[var(--focus)]" />
          <div className="mt-3 grid gap-2 text-sm text-[var(--foreground-muted)] sm:grid-cols-2">
            <label className="flex items-start gap-2 rounded-[var(--radius-md)] bg-[var(--surface)] p-3">
              <input
                type="checkbox"
                checked={allowAiView}
                onChange={(event) => {
                  setAllowAiView(event.target.checked);
                  if (!event.target.checked) setAllowMemory(false);
                }}
              />
              <span><strong className="text-[var(--foreground)]">允许 AI 查看</strong><br />可用于今晚的共同日记。</span>
            </label>
            <label className="flex items-start gap-2 rounded-[var(--radius-md)] bg-[var(--surface)] p-3">
              <input
                type="checkbox"
                checked={allowMemory}
                onChange={(event) => {
                  setAllowMemory(event.target.checked);
                  if (event.target.checked) setAllowAiView(true);
                }}
              />
              <span><strong className="text-[var(--foreground)]">允许记住</strong><br />作为长期记忆整理的事实证据。</span>
            </label>
          </div>
          <div className="mt-3 flex justify-end">
            <Button type="submit" disabled={!draft.trim() || createEntry.isPending}><CheckIcon size={17} />保存</Button>
          </div>
        </form>
      ) : null}

      <div className="mt-8 space-y-8">
        {groups.map(([date, datedEntries]) => (
          <section key={date} aria-labelledby={`diary-${date}`}>
            <h2 id={`diary-${date}`} className="mb-3 text-sm font-semibold text-[var(--foreground-muted)]">{displayDate(date)}</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {datedEntries.map((entry) => {
                const mine = entry.author === "user";
                const editing = editingId === entry.id;
                return (
                  <article key={entry.id} className="flex min-h-52 flex-col rounded-[var(--radius-lg)] bg-[var(--surface)] p-5">
                    <header className="flex items-center justify-between gap-3 text-xs text-[var(--foreground-faint)]">
                      <span className="flex items-center gap-2"><BookOpenTextIcon size={17} className="text-[var(--accent)]" />{mine ? "你写的" : `${companionName}写的`}</span>
                      {!mine ? <span>只读</span> : null}
                    </header>
                    {editing ? (
                      <textarea autoFocus value={editingContent} maxLength={20_000} rows={6} onChange={(event) => setEditingContent(event.target.value)} className="mt-4 w-full flex-1 resize-y rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface-raised)] p-3 text-[15px] leading-7 outline-none focus:ring-2 focus:ring-[var(--focus)]" />
                    ) : (
                      <p className="mt-4 whitespace-pre-wrap break-words text-[15px] leading-7">{entry.content}</p>
                    )}
                    {mine ? (
                      <div className="mt-auto flex flex-wrap gap-2 pt-5">
                        {editing ? (
                          <>
                            <Button type="button" variant="secondary" disabled={!editingContent.trim() || updateEntry.isPending} onClick={() => updateEntry.mutate({ id: entry.id, changes: { content: editingContent.trim() } })}><CheckIcon size={16} />保存</Button>
                            <Button type="button" variant="ghost" onClick={() => { setEditingId(""); setEditingContent(""); }}><XIcon size={16} />取消</Button>
                          </>
                        ) : (
                          <>
                            <Button type="button" variant="secondary" onClick={() => { setEditingId(entry.id); setEditingContent(entry.content); }}><PencilSimpleIcon size={16} />编辑</Button>
                            <Button type="button" variant="ghost" disabled={deleteEntry.isPending} onClick={() => { if (window.confirm("确定删除这篇日记吗？")) deleteEntry.mutate(entry.id); }}><TrashIcon size={16} />删除</Button>
                          </>
                        )}
                        <label className="ml-auto flex items-center gap-2 text-xs text-[var(--foreground-muted)]">
                          <input
                            type="checkbox"
                            checked={entry.allow_ai_view}
                            disabled={updateEntry.isPending}
                            onChange={(event) => updateEntry.mutate({
                              id: entry.id,
                              changes: {
                                allow_ai_view: event.target.checked,
                                ...(event.target.checked ? {} : { allow_memory: false }),
                              },
                            })}
                          />
                          AI 可查看
                        </label>
                        <label className="flex items-center gap-2 text-xs text-[var(--foreground-muted)]">
                          <input
                            type="checkbox"
                            checked={entry.allow_memory}
                            disabled={updateEntry.isPending}
                            onChange={(event) => updateEntry.mutate({
                              id: entry.id,
                              changes: {
                                allow_memory: event.target.checked,
                                ...(event.target.checked ? { allow_ai_view: true } : {}),
                              },
                            })}
                          />
                          允许记住
                        </label>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </section>
        ))}
        {!groups.length ? (
          <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] p-8">
            <h2 className="font-semibold">日记还是空的</h2>
            <p className="mt-2 text-sm leading-6 text-[var(--foreground-muted)]">先写下今天的一件小事吧。</p>
          </div>
        ) : null}
      </div>
    </PageFrame>
  );
}

function PageFrame({ children }: { children: React.ReactNode }) {
  return <section className="mx-auto w-full max-w-5xl px-5 py-7 sm:px-9 sm:py-10">{children}</section>;
}
