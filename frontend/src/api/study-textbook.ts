import { requestJson } from "./client";

export type TextbookBook = {
  book_id: string;
  title: string;
  sections: number;
  updated_at: string;
};

export type TextbookHit = {
  book_id: string;
  book_title: string;
  section_id: string;
  title: string;
  chapter: string;
  sequence: number;
  score: number;
  cached: boolean;
};

export type TextbookStats = {
  root?: string;
  sections: number;
  text_bytes: number;
  temp_bytes: number;
  max_bytes: number;
  books: number | { book_id: string }[];
  index_bytes: number;
  free_bytes: number;
  total_bytes: number;
};

export type TextbookSection = {
  book_id: string;
  book_title: string;
  section_id: string;
  title: string;
  chapter: string;
  cached: boolean;
  chars: number;
  resource_id: string;
  sha256?: string;
  preview?: string;
  quality?: {
    ok: boolean;
    chars: number;
    lines: number;
    duplicate_ratio: number;
    unknown_ratio: number;
    reasons: string[];
  };
  mode?: string;
  screens?: number;
  stop_reason?: string;
};

const root = "/api/study/textbook";

export const textbookApi = {
  books: () => requestJson<{ books: TextbookBook[] }>(`${root}/books`),
  stats: () => requestJson<TextbookStats>(`${root}/stats`),
  sync: (book_id: string, title: string) =>
    requestJson<{ book_id: string; title: string; sections: unknown[] }>(`${root}/index`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ book_id, title, from_device: true }),
    }),
  locate: (query: string, book_id?: string) =>
    requestJson<{ hits: TextbookHit[] }>(`${root}/locate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, book_id: book_id || undefined, limit: 5 }),
    }),
  collect: (book_id: string, section_id: string, force = false) =>
    requestJson<TextbookSection>(`${root}/collect`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ book_id, section_id, force }),
    }),
  cleanup: (max_bytes?: number) =>
    requestJson<{ removed_sections: number; freed_bytes: number; stats: TextbookStats }>(
      `${root}/cleanup`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(max_bytes ? { max_bytes } : {}),
      },
    ),
  release: (book_id: string, section_ids: string[]) =>
    requestJson<{ sections: number; resources: number }>(`${root}/release`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ book_id, section_ids }),
    }),
};

export function formatBytes(value: number): string {
  if (!value) return "0 MB";
  const mb = value / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`;
}
