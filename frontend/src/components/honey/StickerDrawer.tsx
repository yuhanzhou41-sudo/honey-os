import { PlusIcon, TrashIcon, XIcon } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

import {
  deleteSticker,
  listStickers,
  stickerMediaUrl,
  stickerPreviewUrl,
  STICKER_REACTIONS,
  uploadSticker,
  type StickerItem,
  type StickerSort,
  type StickerStatus,
} from "../../api/stickers";
import { Button } from "../ui/Button";

function sizeLabel(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function StickerDrawer({
  onClose,
  onSendSticker,
  onStatusChange,
}: {
  onClose: () => void;
  onSendSticker: (item: StickerItem) => void;
  onStatusChange?: (status: StickerStatus) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [status, setStatus] = useState<StickerStatus | null>(null);
  const [stickers, setStickers] = useState<StickerItem[]>([]);
  const [tag, setTag] = useState<(typeof STICKER_REACTIONS)[number][0]>("happy");
  const [sort, setSort] = useState<StickerSort>("recent");
  const [busy, setBusy] = useState(false);
  const [manageMode, setManageMode] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh(nextSort = sort) {
    const result = await listStickers({ sort: nextSort, limit: 24 });
    setStickers(result.stickers);
    setStatus(result.status);
    onStatusChange?.(result.status);
  }

  useEffect(() => {
    void refresh().catch(() => setError("表情包暂时没有加载成功"));
  }, []);

  async function choose(file: File | undefined) {
    if (!file || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await uploadSticker(file, tag);
      setStatus(result.status);
      onStatusChange?.(result.status);
      setNotice(`已添加 ${result.sticker.original_name}`);
      await refresh(sort);
    } catch (uploadError) {
      const message = uploadError instanceof Error ? uploadError.message : "";
      setError(
        message === "sticker_limit_reached"
          ? "已经达到 400 张上限，先整理一些再添加吧。"
          : message === "sticker_file_size_invalid"
            ? "这张表情包太大了，单张最多 15 MB。"
            : message === "sticker_dimensions_invalid"
              ? "这张图片尺寸太大了，请换一张更适合聊天的表情。"
              : "只支持有效的 GIF、WebP、PNG 文件。",
      );
    } finally {
      setBusy(false);
    }
  }

  async function remove(item: StickerItem) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await deleteSticker(item.id);
      setStatus(result.status);
      onStatusChange?.(result.status);
      setSelectedId(null);
      setPreviewId(null);
      setNotice(`已删除 ${item.original_name}`);
      await refresh(sort);
    } catch {
      setError("这张表情包没有删除成功，请再试一次。");
    } finally {
      setBusy(false);
    }
  }

  async function changeSort(next: StickerSort) {
    setSort(next);
    setError("");
    setNotice("");
    setSelectedId(null);
    try {
      await refresh(next);
    } catch {
      setError("表情包暂时没有加载成功");
    }
  }

  function activate(item: StickerItem) {
    if (manageMode) {
      setSelectedId((current) => current === item.id ? null : item.id);
      return;
    }
    onSendSticker(item);
  }

  return (
    <section
      className="absolute bottom-full left-0 z-30 mb-3 w-[min(28rem,calc(100vw-2rem))] overflow-hidden rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-raised)] shadow-[0_18px_48px_rgba(56,48,39,0.18)]"
      aria-label="Honey 表情包"
    >
      <header className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
        <div className="min-w-0 flex-1">
          <p className="font-medium">Honey 的表情包</p>
          <p className="text-xs text-[var(--foreground-muted)]">
            {status ? `${status.count} / ${status.limit} · ${sizeLabel(status.total_bytes)}` : "正在读取…"}
          </p>
        </div>
        <Button
          type="button"
          variant={manageMode ? "secondary" : "ghost"}
          onClick={() => {
            setManageMode((current) => !current);
            setSelectedId(null);
          }}
        >
          {manageMode ? "完成" : "整理"}
        </Button>
        <Button type="button" size="icon" variant="ghost" aria-label="关闭表情包" onClick={onClose}>
          <XIcon size={16} />
        </Button>
      </header>

      {status?.warning ? (
        <div className="border-b border-[var(--border)] bg-[var(--surface-subtle)] px-4 py-2 text-xs">
          {status.full
            ? "已经达到 400 张上限。Honey 不会自动删除，请先整理再添加。"
            : `已经有 ${status.count} 张，接近 400 张上限，可以开始整理不常用的表情了。`}
        </div>
      ) : null}

      <div className="flex items-center gap-1 px-3 pt-3">
        <Button type="button" variant={sort === "recent" ? "secondary" : "ghost"} onClick={() => void changeSort("recent")}>最近</Button>
        <Button type="button" variant={sort === "least_used" ? "secondary" : "ghost"} onClick={() => void changeSort("least_used")}>少用</Button>
        <Button type="button" variant={sort === "largest" ? "secondary" : "ghost"} onClick={() => void changeSort("largest")}>最大</Button>
        <span className="ml-auto text-xs text-[var(--foreground-muted)]">
          {manageMode ? "点一下选中，再点垃圾桶删除" : "点一下直接发送"}
        </span>
      </div>

      <div className="max-h-[22rem] overflow-y-auto p-3">
        {stickers.length ? (
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
            {stickers.map((item) => {
              const selected = selectedId === item.id;
              const animated = previewId === item.id;
              return (
                <div
                  key={item.id}
                  className={[
                    "group relative aspect-square overflow-hidden rounded-[var(--radius-md)] border bg-[var(--surface)]",
                    selected
                      ? "border-[var(--foreground)] ring-2 ring-[var(--focus)]"
                      : "border-[var(--border)]",
                  ].join(" ")}
                >
                  <button
                    type="button"
                    className="h-full w-full outline-none"
                    aria-label={manageMode ? `选择 ${item.original_name}` : `发送 ${item.original_name}`}
                    aria-pressed={manageMode ? selected : undefined}
                    title={`${item.original_name} · 用过 ${item.usage_count} 次`}
                    onClick={() => activate(item)}
                    onMouseEnter={() => setPreviewId(item.id)}
                    onMouseLeave={() => setPreviewId((current) => current === item.id ? null : current)}
                    onFocus={() => setPreviewId(item.id)}
                    onBlur={() => setPreviewId((current) => current === item.id ? null : current)}
                  >
                    <img
                      src={animated ? stickerMediaUrl(item.id) : stickerPreviewUrl(item.id)}
                      alt={item.original_name}
                      className="h-full w-full object-contain"
                      loading="lazy"
                      decoding="async"
                    />
                  </button>

                  {manageMode && selected ? (
                    <button
                      type="button"
                      className="absolute right-1 top-1 grid size-8 place-items-center rounded-full bg-black/70 text-white shadow-md"
                      aria-label={`删除 ${item.original_name}`}
                      title="从本地表情包删除"
                      disabled={busy}
                      onClick={(event) => {
                        event.stopPropagation();
                        void remove(item);
                      }}
                    >
                      <TrashIcon size={15} />
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="px-3 py-8 text-center text-sm text-[var(--foreground-muted)]">
            还没有本地表情包。Honey 会继续使用 Noto 动态表情。
          </div>
        )}

        <div className="mt-3 flex items-center gap-2 border-t border-[var(--border)] pt-3">
          <input
            ref={inputRef}
            type="file"
            accept=".gif,.webp,.png,image/gif,image/webp,image/png"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              void choose(file);
            }}
          />
          <select
            value={tag}
            onChange={(event) => setTag(event.target.value as typeof tag)}
            className="h-9 min-w-0 flex-1 rounded-[var(--radius-md)] border border-[var(--border-strong)] bg-[var(--surface)] px-2 text-sm"
            aria-label="新表情分类"
          >
            {STICKER_REACTIONS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
          <Button
            type="button"
            variant="secondary"
            disabled={busy || status?.full}
            aria-label="添加本地表情包"
            title={status?.full ? "已经达到 400 张上限" : "添加 GIF / WebP / PNG"}
            onClick={() => inputRef.current?.click()}
          >
            <PlusIcon size={16} />
            添加
          </Button>
        </div>
      </div>

      {notice ? <p className="border-t border-[var(--border)] px-4 py-2 text-xs text-[var(--foreground-muted)]">{notice}</p> : null}
      {error ? <p className="border-t border-[var(--border)] px-4 py-2 text-xs text-[var(--danger)]">{error}</p> : null}
    </section>
  );
}
