import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import {
  listAttachments,
  uploadAttachment,
  type Attachment,
} from "../../api/attachments";
import {
  createStudyResource,
  deleteStudyResource,
  getStudyResourceContent,
  listStudyResources,
  searchStudyResources,
  type StudyResource,
  type StudyResourceSearchHit,
} from "../../api/study";

const attachmentsKey = ["attachments"] as const;
const resourcesKey = ["study", "resources"] as const;

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

  const upload = useMutation({
    mutationFn: (file: File) => uploadAttachment(file, "study"),
    onSuccess: ({ attachment }) => {
      setSelectedAttachmentId(attachment.id);
      setTitle(attachment.original_filename);
      qc.invalidateQueries({ queryKey: attachmentsKey });
    },
  });

  const create = useMutation({
    mutationFn: async () => {
      if (!selectedAttachmentId) throw new Error("请先上传或选择一个支持的学习资料");
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
    upload.error ||
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

          <label className="mt-4 block cursor-pointer rounded-[var(--radius-md)] border border-dashed border-[var(--border-strong)] px-3 py-4 text-center text-sm hover:bg-[var(--surface)]">
            {upload.isPending ? "上传中…" : "＋ 上传学习资料"}
            <input
              type="file"
              className="hidden"
              accept=".txt,.md,.markdown,.json,.csv,.tsv,.xml,.pdf,.docx,.pptx,.xlsx,text/*,application/json,application/xml,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              disabled={upload.isPending}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate(file);
                event.currentTarget.value = "";
              }}
            />
          </label>

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
                      onClick={() => remove.mutate(id)}
                      disabled={remove.isPending}
                      className="mt-3 text-xs text-[var(--foreground-muted)] hover:text-red-500 disabled:opacity-45"
                    >
                      从学习资料库删除
                    </button>
                  </article>
                );
              })
            ) : (
              <div className="rounded-[var(--radius-lg)] border border-dashed border-[var(--border-strong)] px-5 py-12 text-center">
                <p className="text-sm font-medium">还没有匹配的学习资料</p>
                <p className="mt-1 text-xs text-[var(--foreground-muted)]">
                  左侧上传文本资料，或调整搜索条件。
                </p>
              </div>
            )}
          </section>

          <section className="min-w-0 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] p-4 sm:p-5">
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
