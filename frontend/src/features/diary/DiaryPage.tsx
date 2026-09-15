import { BookOpenTextIcon, CheckIcon, PencilSimpleIcon, PlusIcon, TrashIcon, XIcon } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import {
  createCompanionDiaryEntry,
  deleteCompanionDiaryEntry,
  fetchCompanionDiary,
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

export function DiaryPage() {
  const companionName = useHoneyStore((state) => state.name);
  const queryClient = useQueryClient();
  const [composing, setComposing] = useState(false);
  const [entryDate, setEntryDate] = useState(localDate);
  const [draft, setDraft] = useState("");
  const [editingId, setEditingId] = useState("");
  const [editingContent, setEditingContent] = useState("");
  const [notice, setNotice] = useState("");

  const diary = useQuery({ queryKey: diaryKey, queryFn: fetchCompanionDiary });
  const entries = diary.data?.entries ?? [];
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
    mutationFn: ({ id, content }: { id: string; content: string }) => updateCompanionDiaryEntry(id, content),
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

  function submitNew(event: FormEvent) {
    event.preventDefault();
    const content = draft.trim();
    if (!content) return;
    setNotice("");
    createEntry.mutate({ entry_date: entryDate, content });
  }

  if (diary.isLoading) return <PageFrame><LoadingState /></PageFrame>;
  if (diary.isError) return <PageFrame><ErrorState /></PageFrame>;

  return (
    <PageFrame>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PageHeader title="共同日记" description={`你和${companionName}写下的日常，会按日期一起留在这里。`} />
        <Button type="button" onClick={() => setComposing(true)} disabled={composing}>
          <PlusIcon size={17} />写一篇
        </Button>
      </div>

      {notice ? <p className="mt-4 text-sm text-[var(--foreground-muted)]" role="status">{notice}</p> : null}

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
                            <Button type="button" variant="secondary" disabled={!editingContent.trim() || updateEntry.isPending} onClick={() => updateEntry.mutate({ id: entry.id, content: editingContent.trim() })}><CheckIcon size={16} />保存</Button>
                            <Button type="button" variant="ghost" onClick={() => { setEditingId(""); setEditingContent(""); }}><XIcon size={16} />取消</Button>
                          </>
                        ) : (
                          <>
                            <Button type="button" variant="secondary" onClick={() => { setEditingId(entry.id); setEditingContent(entry.content); }}><PencilSimpleIcon size={16} />编辑</Button>
                            <Button type="button" variant="ghost" disabled={deleteEntry.isPending} onClick={() => { if (window.confirm("确定删除这篇日记吗？")) deleteEntry.mutate(entry.id); }}><TrashIcon size={16} />删除</Button>
                          </>
                        )}
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
