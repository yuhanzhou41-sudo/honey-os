import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  formatBytes,
  textbookApi,
  type TextbookHit,
  type TextbookSection,
} from "../../api/study-textbook";

const field =
  "mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2 text-sm";
const action = "rounded-full border border-[var(--border)] px-3 py-1.5 text-sm disabled:opacity-50";
const primary =
  "rounded-full bg-[var(--accent)] px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50";

export function StudyTextbookPanel() {
  const client = useQueryClient();
  const books = useQuery({ queryKey: ["study", "textbook", "books"], queryFn: textbookApi.books });
  const stats = useQuery({ queryKey: ["study", "textbook", "stats"], queryFn: textbookApi.stats });
  const [bookId, setBookId] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<TextbookHit[]>([]);
  const [section, setSection] = useState<TextbookSection>();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [syncId, setSyncId] = useState("renwei_xunhuan");
  const [syncTitle, setSyncTitle] = useState("循环系统疾病（第2版）");

  useEffect(() => {
    if (!bookId && books.data?.books.length) setBookId(books.data.books[0].book_id);
  }, [books.data, bookId]);

  async function run(label: string, work: () => Promise<string>) {
    setBusy(label);
    setMessage("");
    try {
      setMessage(await work());
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "操作失败，请重试。");
    } finally {
      setBusy("");
    }
  }

  const book = books.data?.books.find((item) => item.book_id === bookId);

  return (
    <div className="space-y-5 text-sm">
      <section className="space-y-2">
        <h3 className="font-medium">教材目录</h3>
        {books.data?.books.length ? (
          <label className="block">
            当前教材
            <select className={field} value={bookId} onChange={(event) => setBookId(event.target.value)}>
              {books.data.books.map((item) => (
                <option key={item.book_id} value={item.book_id}>
                  {item.title}（{item.sections} 节）
                </option>
              ))}
            </select>
          </label>
        ) : (
          <p className="text-[var(--foreground-muted)]">
            还没有目录索引。把 APP 打开到任意阅读页，填好编号后点“同步目录”。
          </p>
        )}
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="block">
            教材编号
            <input className={field} value={syncId} onChange={(event) => setSyncId(event.target.value)} />
          </label>
          <label className="block">
            教材名称
            <input className={field} value={syncTitle} onChange={(event) => setSyncTitle(event.target.value)} />
          </label>
        </div>
        <button type="button" className={action} disabled={Boolean(busy)}
          onClick={() => void run("sync", async () => {
            const result = await textbookApi.sync(syncId.trim(), syncTitle.trim());
            await client.invalidateQueries({ queryKey: ["study", "textbook"] });
            return `目录已同步：${result.sections.length} 节。`;
          })}>
          {busy === "sync" ? "正在展开目录…" : "同步目录"}
        </button>
      </section>

      <section className="space-y-2">
        <h3 className="font-medium">按问题定位章节</h3>
        <div className="flex gap-2">
          <input className={field} placeholder="例如：周围血管、心力衰竭" value={query}
            onChange={(event) => setQuery(event.target.value)} />
          <button type="button" className={primary} disabled={!bookId || !query.trim() || Boolean(busy)}
            onClick={() => void run("locate", async () => {
              const result = await textbookApi.locate(query.trim(), bookId);
              setHits(result.hits);
              return result.hits.length ? `找到 ${result.hits.length} 节。` : "没有匹配的章节，换个关键词试试。";
            })}>
            定位
          </button>
        </div>
        {hits.length > 0 && (
          <ul className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {hits.map((hit) => (
              <li key={hit.section_id} className="flex items-center justify-between gap-3 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate">{hit.title}</p>
                  <p className="truncate text-xs text-[var(--foreground-muted)]">
                    {hit.chapter}{hit.cached ? " · 已缓存" : ""}
                  </p>
                </div>
                <button type="button" className={action} disabled={Boolean(busy)}
                  onClick={() => void run("collect", async () => {
                    const result = await textbookApi.collect(hit.book_id, hit.section_id, true);
                    setSection(result);
                    await client.invalidateQueries({ queryKey: ["study", "textbook"] });
                    return `已采集 ${result.chars} 字，可直接用于答疑、闪卡和出题。`;
                  })}>
                  {hit.cached ? "重新采集" : "采集"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {section && (
        <section className="space-y-2">
          <h3 className="font-medium">采集结果</h3>
          <p className="text-xs text-[var(--foreground-muted)]">
            {section.chapter} {section.title} · {section.chars} 字
            {section.quality ? ` · 质量${section.quality.ok ? "通过" : "存疑"}` : ""}
          </p>
          {section.preview && (
            <p className="max-h-32 overflow-y-auto rounded-lg bg-[var(--surface)] p-3 leading-6">
              {section.preview}…
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            <button type="button" className={action} disabled={Boolean(busy)}
              onClick={() => void run("release", async () => {
                const result = await textbookApi.release(section.book_id, [section.section_id]);
                setSection(undefined);
                setHits((rows) => rows.map((row) =>
                  row.section_id === section.section_id ? { ...row, cached: false } : row));
                await client.invalidateQueries({ queryKey: ["study", "textbook"] });
                return `已释放 ${result.sections} 节正文与派生复习资料。`;
              })}>
              完成复习，释放本节
            </button>
          </div>
        </section>
      )}

      <section className="space-y-2 border-t border-[var(--border)] pt-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-[var(--foreground-muted)]">
            {stats.data
              ? `缓存 ${formatBytes(stats.data.text_bytes)} / 上限 ${formatBytes(stats.data.max_bytes)}，临时 ${formatBytes(stats.data.temp_bytes)}`
              : "正在读取缓存占用…"}
          </p>
          <button type="button" className={action} disabled={Boolean(busy)}
            onClick={() => void run("cleanup", async () => {
              const result = await textbookApi.cleanup();
              await client.invalidateQueries({ queryKey: ["study", "textbook"] });
              return `已清理 ${result.removed_sections} 节，释放 ${formatBytes(result.freed_bytes)}。`;
            })}>
            清理缓存
          </button>
        </div>
        {book && (
          <p className="text-xs text-[var(--foreground-muted)]">
            当前教材 {book.title} 共 {book.sections} 节；只有被采集或引用过的章节才会占用空间。
          </p>
        )}
      </section>

      {message && <p className="text-xs text-[var(--foreground-muted)]">{message}</p>}
    </div>
  );
}
