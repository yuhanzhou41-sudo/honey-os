import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  listAttachments,
  type Attachment,
} from "../../api/attachments";
import {
  clearExpiredStudyFiles,
  createStudyResource,
  getStudyResourceStorage,
  listStudyLibraryStorage,
  referenceLocalStudyFile,
  deleteStudyResource,
  getStudyResourceContent,
  listStudyResources,
  searchStudyResources,
  type StudyResource,
  type StudyResourceSearchHit,
} from "../../api/study";

const attachmentsKey = ["attachments"] as const;
const resourcesKey = ["study", "resources"] as const;
const storageKey = ["study", "storage"] as const;

const sourceStatusLabels = {
  online: "原文件可访问",
  offline: "原文件暂不可访问",
  changed: "原文件内容可能已更改",
  managed: "已有附件",
};

type LibraryRow = StudyResource | StudyResourceSearchHit;

function rowId(row: LibraryRow) {
  return "resource_id" in row ? row.resource_id : row.id;
}

function rowSnippet(row: LibraryRow) {
  return "snippet" in row ? row.snippet : "";
}

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function isStudySupportedAttachment(attachment: Attachment) {
  const mime = (
    attachment.inferred_mime_type ||
    attachment.declared_mime_type ||
    ""
  ).toLowerCase();
  const filename = attachment.original_filename.toLowerCase();
  return (
    mime.startsWith("text/") ||
    ["application/json", "application/xml"].includes(mime) ||
    [".txt", ".md", ".markdown", ".json", ".csv", ".tsv", ".xml", ".pdf", ".docx", ".pptx", ".xlsx"].some(
      (suffix) => filename.endsWith(suffix),
    )
  );
}

export function StudyLibraryPanel() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [courseFilter, setCourseFilter] = useState("");
  const [selectedAttachmentId, setSelectedAttachmentId] = useState("");
  const [selectedResourceId, setSelectedResourceId] = useState("");
  const [title, setTitle] = useState("");
  const [course, setCourse] = useState("");
  const [resourceType, setResourceType] = useState("notes");
  const [sourcePath, setSourcePath] = useState("");
  const [relinkPath, setRelinkPath] = useState("");
  const [notice, setNotice] = useState("");

  const attachmentsQuery = useQuery({
    queryKey: attachmentsKey,
    queryFn: listAttachments,
  });

  const resourcesQuery = useQuery({
    queryKey: [...resourcesKey, query.trim(), courseFilter.trim()],
    queryFn: async () => {
      const q = query.trim();
      const subject = courseFilter.trim();
      if (q || subject) {
        const response = await searchStudyResources({
          q,
          course_or_subject: subject,
          limit: 50,
        });
        return response.results as LibraryRow[];
      }
      const response = await listStudyResources();
      return response.resources as LibraryRow[];
    },
  });

  const storageQuery = useQuery({
    queryKey: storageKey,
    queryFn: listStudyLibraryStorage,
  });
  const sourceQuery = useQuery({
    queryKey: [...resourcesKey, "source", selectedResourceId],
    queryFn: () => getStudyResourceStorage(selectedResourceId),
    enabled: Boolean(selectedResourceId),
  });

  const contentQuery = useQuery({
    queryKey: [...resourcesKey, "content", selectedResourceId],
    queryFn: () => getStudyResourceContent(selectedResourceId),
    enabled: Boolean(selectedResourceId),
  });

  const attachments = attachmentsQuery.data?.attachments ?? [];
  const supportedAttachments = useMemo(
    () =>
      attachments.filter(
        (item) => item.status === "ready" && isStudySupportedAttachment(item),
      ),
    [attachments],
  );
  const rows = resourcesQuery.data ?? [];

  useEffect(() => {
    if (
      selectedAttachmentId &&
      !supportedAttachments.some((item) => item.id === selectedAttachmentId)
    ) {
      setSelectedAttachmentId("");
    }
  }, [selectedAttachmentId, supportedAttachments]);

  const selectedAttachment = supportedAttachments.find(
    (item) => item.id === selectedAttachmentId,
  );

  const refreshResources = () =>
    qc.invalidateQueries({ queryKey: resourcesKey });

  const reference = useMutation({
    mutationFn: ({ path, existingId }: { path: string; existingId?: string }) =>
      referenceLocalStudyFile(path, existingId),
    onSuccess: ({ resource, reused }, { existingId }) => {
      setSelectedResourceId(resource.id);
      setSourcePath("");
      setRelinkPath("");
      setNotice(existingId ? "已重新定位原文件" : reused ? "已复用资料库中的相同文档" : "已引用原文件");
      refreshResources();
    },
  });
  const clean = useMutation({
    mutationFn: clearExpiredStudyFiles,
    onSuccess: ({ freed_bytes }) => {
      setNotice(`已释放 ${formatBytes(freed_bytes)}`);
      qc.invalidateQueries({ queryKey: storageKey });
    },
  });

  const create = useMutation({
    mutationFn: async () => {
      if (!selectedAttachmentId) throw new Error("请选择已有的学习附件");
      const normalizedTitle =
        title.trim() || selectedAttachment?.original_filename || "";
      if (!normalizedTitle) throw new Error("请输入资料名称");
      return createStudyResource({
        attachment_id: selectedAttachmentId,
        title: normalizedTitle,
        resource_type: resourceType.trim() || "notes",
        course_or_subject: course.trim(),
        metadata: {},
      });
    },
    onSuccess: ({ resource }) => {
      setSelectedResourceId(resource.id);
      setTitle("");
      setCourse("");
      refreshResources();
    },
  });

  const remove = useMutation({
    mutationFn: (resourceId: string) => deleteStudyResource(resourceId),
    onSuccess: (_, resourceId) => {
      if (selectedResourceId === resourceId) setSelectedResourceId("");
      refreshResources();
    },
  });

  const error =
    attachmentsQuery.error ||
    resourcesQuery.error ||
    reference.error || clean.error || storageQuery.error || sourceQuery.error ||
    create.error ||
    remove.error;

  return (
    <div className="mt-6 grid gap-5 xl:grid-cols-[330px_minmax(0,1fr)]">
      <aside className="space-y-4">
        <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[var(--foreground-muted)]">
            添加学习资料
          </p>
          <p className="mt-2 text-xs leading-5 text-[var(--foreground-muted)]">
            Phase 4 第一版支持 UTF-8 文本、Markdown、JSON、CSV、TSV 和 XML。
            支持文本层 PDF、DOCX、PPTX、XLSX；扫描 PDF 与图片内容暂不做 OCR / 视觉理解。
          </p>

          <form className="mt-3 space-y-2" onSubmit={(event) => {
            event.preventDefault();
            if (sourcePath.trim()) reference.mutate({ path: sourcePath });
          }}>
            <label className="block text-xs" htmlFor="study-source-path">原文件路径</label>
            <input id="study-source-path" value={sourcePath} onChange={(event) => setSourcePath(event.target.value)}
              placeholder="粘贴完整 Windows 文件路径"
              className="w-full rounded border border-[var(--border)] px-2 py-2 text-sm" />
            <button type="submit" disabled={!sourcePath.trim() || reference.isPending}
              className="rounded border border-[var(--border)] px-3 py-2 text-sm disabled:opacity-45">
              {reference.isPending ? "正在提取…" : "引用本机文件"}
            </button>
            <p className="text-xs text-[var(--foreground-muted)]">原文件保留在原位置，资料库只保存引用和索引。</p>
          </form>

          <div className="mt-4">
            <label className="text-xs text-[var(--foreground-muted)]">
              已有附件
            </label>
            <select
              value={selectedAttachmentId}
              onChange={(event) => {
                const id = event.target.value;
                setSelectedAttachmentId(id);
                const attachment = supportedAttachments.find(
                  (item) => item.id === id,
                );
                if (attachment) setTitle(attachment.original_filename);
              }}
              className="mt-1 w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
            >
              <option value="">选择可索引附件</option>
              {supportedAttachments.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.original_filename} · {formatBytes(item.size_bytes)}
                </option>
              ))}
            </select>
          </div>

          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="资料名称"
            className="mt-3 w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
          />
          <input
            value={course}
            onChange={(event) => setCourse(event.target.value)}
            placeholder="课程 / 科目（可选）"
            className="mt-2 w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
          />
          <input
            value={resourceType}
            onChange={(event) => setResourceType(event.target.value)}
            placeholder="资料类型，例如 notes"
            className="mt-2 w-full rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
          />

          <button
            type="button"
            onClick={() => create.mutate()}
            disabled={create.isPending || !selectedAttachmentId}
            className="mt-3 w-full rounded-[var(--radius-md)] bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white disabled:opacity-45"
          >
            {create.isPending ? "建立索引中…" : "加入学习资料库"}
          </button>

          {error ? (
            <p className="mt-3 text-xs leading-5 text-red-500">
              {messageOf(error)}
            </p>
          ) : null}
        </section>
        <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4">
          <h3 className="text-sm font-medium">存储管理</h3>
          <p className="mt-2 text-xs text-[var(--foreground-muted)]">打开这里会自动清理超过 24 小时的临时文件。</p>
          {(storageQuery.data?.libraries ?? []).map((library) => (
            <div key={library.library_id} className="mt-2 text-xs">
              <p>{library.name} · {library.online ? `临时文件 ${formatBytes(library.temp_bytes)}` : "磁盘离线"}</p>
              <button type="button" className="mt-1 underline disabled:opacity-45"
                disabled={!library.online || clean.isPending}
                onClick={() => clean.mutate(library.library_id)}>清理过期临时文件</button>
            </div>
          ))}
          {notice ? <p className="mt-2 text-xs" role="status">{notice}</p> : null}
        </section>
      </aside>

      <main className="min-w-0 space-y-4">
        <section className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4 sm:p-5">
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索标题、课程或资料正文"
              className="min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm"
            />
            <input
              value={courseFilter}
              onChange={(event) => setCourseFilter(event.target.value)}
              placeholder="按课程精确筛选"
              className="rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-3 py-2.5 text-sm sm:w-56"
            />
          </div>
          <div className="mt-3 flex items-center justify-between text-xs text-[var(--foreground-muted)]">
            <span>{rows.length} 条资料</span>
            <span>{query.trim() ? "SQLite FTS5 搜索" : "资料库列表"}</span>
          </div>
        </section>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <section className="min-w-0 space-y-2">
            {resourcesQuery.isLoading ? (
              <div className="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] px-4 py-8 text-center text-sm text-[var(--foreground-muted)]">
                正在读取学习资料…
              </div>
            ) : rows.length ? (
              rows.map((row) => {
                const id = rowId(row);
                const active = id === selectedResourceId;
                return (
                  <article
                    key={id}
                    className={`rounded-[var(--radius-lg)] border p-4 transition ${
                      active
                        ? "border-[var(--accent)] bg-[var(--surface-raised)]"
                        : "border-[var(--border)] bg-[var(--surface-raised)]"
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setSelectedResourceId(id)}
                      className="w-full text-left"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-medium">{row.title}</h3>
                        {row.course_or_subject ? (
                          <span className="rounded-full bg-[var(--surface)] px-2 py-1 text-[11px] text-[var(--foreground-muted)]">
                            {row.course_or_subject}
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-xs text-[var(--foreground-muted)]">
                        {row.resource_type}
                      </p>
                      {rowSnippet(row) ? (
                        <p className="mt-3 line-clamp-4 whitespace-pre-wrap text-sm leading-6 text-[var(--foreground-muted)]">
                          {rowSnippet(row)
                            .replaceAll(">>>", "")
                            .replaceAll("<<<", "")}
                        </p>
                      ) : null}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm("移除此资料及索引？原文件和已有附件会保留。")) remove.mutate(id);
                      }}
                      disabled={remove.isPending}
                      className="mt-3 text-xs text-[var(--foreground-muted)] hover:text-red-500 disabled:opacity-45"
                    >
                      移除资料和索引
                    </button>
                  </article>
                );
              })
            ) : (
              <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] px-5 py-12 text-center">
                <p className="text-sm font-medium">还没有匹配的学习资料</p>
                <p className="mt-1 text-xs text-[var(--foreground-muted)]">
                  左侧引用本机资料，或调整搜索条件。
                </p>
              </div>
            )}
          </section>

          <section className="min-w-0 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4 sm:p-5">
            {sourceQuery.data?.storage ? (
              <div className="mb-4 space-y-2 border-b border-[var(--border)] pb-3 text-xs">
                <p>{sourceStatusLabels[sourceQuery.data.storage.source_status]}</p>
                {sourceQuery.data.storage.has_managed_attachment ? (
                  <p className="text-[var(--foreground-muted)]">此资料关联已有附件。移除资料后，该附件仍可供其他功能使用。</p>
                ) : null}
                {sourceQuery.data.storage.source_path ? (
                  <p className="break-all">{sourceQuery.data.storage.source_path}</p>
                ) : null}
                <p>索引正文 {formatBytes(sourceQuery.data.storage.indexed_text_bytes)}
                  {sourceQuery.data.storage.original_bytes !== null
                    ? ` · 原文件 ${formatBytes(sourceQuery.data.storage.original_bytes)}` : ""}
                </p>
                {sourceQuery.data.storage.source_path && sourceQuery.data.storage.source_status !== "online" ? (
                  <form className="flex gap-2" onSubmit={(event) => {
                    event.preventDefault();
                    if (relinkPath.trim()) reference.mutate({ path: relinkPath, existingId: selectedResourceId });
                  }}>
                    <input aria-label="新原文件路径" placeholder="粘贴同一文件的新路径" value={relinkPath}
                      className="min-w-0 flex-1 rounded border border-[var(--border)] px-2 py-1"
                      onChange={(event) => setRelinkPath(event.target.value)} />
                    <button type="submit" disabled={!relinkPath.trim() || reference.isPending}>重新定位</button>
                  </form>
                ) : null}
              </div>
            ) : null}
            {!selectedResourceId ? (
              <div className="py-12 text-center">
                <p className="text-sm font-medium">选择一份资料查看索引正文</p>
                <p className="mt-1 text-xs text-[var(--foreground-muted)]">
                  这里显示的是 Study Library 的派生文本，不是 Personal Memory。
                </p>
              </div>
            ) : contentQuery.isLoading ? (
              <p className="py-8 text-center text-sm text-[var(--foreground-muted)]">
                正在读取正文…
              </p>
            ) : contentQuery.isError ? (
              <p className="text-sm text-red-500">
                {messageOf(contentQuery.error)}
              </p>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
                  <p className="text-sm font-semibold">索引正文</p>
                  <span className="text-xs text-[var(--foreground-muted)]">
                    {contentQuery.data?.content.extraction_kind}
                  </span>
                </div>
                <pre className="mt-4 max-h-[640px] overflow-auto whitespace-pre-wrap break-words font-sans text-sm leading-7 text-[var(--foreground-muted)]">
                  {contentQuery.data?.content.extracted_text}
                </pre>
              </>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
