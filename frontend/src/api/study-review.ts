import { requestJson } from "./client";

export type QuestionInput = {
  prompt: string; options: string[]; correct: number; explanation: string;
  resource_id: string; excerpt: string;
};
type Provenance = {
  kind: "past" | "mock" | "upload" | "web" | null;
  exam: string | null; year: number | null; location: string | null; source_url?: string | null;
};
export type Question = Omit<QuestionInput, "correct" | "explanation"> & Provenance & {
  id: string; source_title: string; latest_correct: number | null;
};
export type Attempt = { id: string; choice: number; correct: number; created_at: string };
export type AnsweredQuestion = Question & { correct?: number; explanation?: string };
type History = { attempts: Attempt[]; question: AnsweredQuestion };
export type Card = { front: string; back: string; excerpt: string };
export type CardSource = { resource_id?: string; question_id?: string; segment?: number };
export type CardPreview = CardSource & { cards: Card[]; source_title: string; partial: boolean; segments: number };
export type SavedCard = Card & {
  id: string; resource_id: string; question_id: string | null; source_title: string;
};
export type StudyAnswer = {
  answer: string;
  citations: { resource_id: string; source_title: string; excerpt: string }[];
};

const review = "/api/study/review";
export function fileData(file: File): Promise<string> {
  if (!file.size || file.size > 6 * 1024 * 1024) throw new Error("请选择 6 MB 以内的非空题目文件。");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("无法读取题目文件，请重选。"));
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(file);
  });
}
const daily = review + "/daily";
export type DailyScope = { keyword: string; resource_id: string; wrong: boolean; kind?: string };
export type Recall = {
  id: string; card_id: string; response: string; created_at: string; rating: number | null; due_at: string | null;
};
export type Quiz = {
  id: string | null; available: number; questions: (Pick<Question, "id" | "prompt" | "options"> & Provenance)[];
};
export type QuizResult = {
  score: number; results: { question: AnsweredQuestion; choice: number; correct: boolean }[];
};
export type DailySummary = {
  date: string; completed: number; tasks: number; attempts: number; correct: number;
  recalls: number; mastered: number; suggestions: string[];
  pending: { id: string; plan: string; title: string }[];
};
export type QuestionDraft = Omit<QuestionInput, "resource_id" | "correct"> & {
  correct: number | null; verified_past?: boolean; exam?: string; year?: number; location?: string;
};
export type ExamSource = { url: string; title: string; description: string };
export type IntakeDraft = {
  source: { id: string; kind: "upload" | "web" | "mock"; title: string; url: string | null };
  text: string; segments: number; questions: QuestionDraft[]; partial?: boolean; warning?: string; documents?: ExamSource[];
};
const attempts = (id: string) => review + "/questions/" + encodeURIComponent(id) + "/attempts";
function post<T>(path: string, body: object) {
  return requestJson<T>(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
}
export const studyReview = {
  uploadDrafts: (filename: string, data: string, segment: number) =>
    post<IntakeDraft>(review + "/intake/upload", { filename, data, segment }),
  searchExams: (topic: string) => post<{ sources: ExamSource[] }>(review + "/intake/search", { topic }),
  webDrafts: (url: string, segment: number) => post<IntakeDraft>(review + "/intake/web", { url, segment }),
  practiceDrafts: (topic: string, plan_id: string | undefined, task_ids: string[]) =>
    post<IntakeDraft>(review + "/intake/generate", { topic, plan_id, task_ids, consent: true }),
  saveIntake: (source_id: string, questions: QuestionDraft[]) =>
    post<{ imported: number }>(review + "/intake/save", { source_id, questions }),
  draw: (scope: DailyScope) =>
    post<{ card: Pick<SavedCard, "id" | "front"> | null; matched: number }>(daily + "/card", scope),
  recall: (cardId: string, id: string, response: string) =>
    post<{ card: SavedCard; recall: Recall }>(daily + "/recall/" + encodeURIComponent(cardId), { id, response }),
  rate: (id: string, rating: number) =>
    post<Recall>(daily + "/rating/" + encodeURIComponent(id), { rating }),
  recalls: () => requestJson<{ recalls: (Recall & { front: string })[] }>(daily + "/recalls"),
  summary: () => requestJson<DailySummary>(daily + "/summary?timezone=" +
    encodeURIComponent(Intl.DateTimeFormat().resolvedOptions().timeZone)),
  quiz: (scope: DailyScope, count: number) => post<Quiz>(daily + "/quiz", { ...scope, count }),
  submitQuiz: (id: string, choices: number[]) =>
    post<QuizResult>(daily + "/quiz/" + encodeURIComponent(id), { choices }),
  questions: () => requestJson<{ questions: Question[] }>(review + "/questions"),
  createQuestion: (value: QuestionInput) => post<{ id: string }>(review + "/questions", value),
  importQuestions: (resource_id: string, kind: "past" | "mock", questions: unknown) =>
    post<{ imported: number }>(review + "/questions/import", { resource_id, kind, questions }),
  previewQuestions: (resource_id: string, segment: number) =>
    post<{ questions: Omit<QuestionInput, "resource_id">[]; segments: number }>(
      review + "/questions/preview", { resource_id, segment }),
  history: (id: string) => requestJson<History>(attempts(id)),
  attempt: (id: string, choice: number, attempt_id: string) =>
    post<{ attempt: Attempt; question: AnsweredQuestion }>(attempts(id), { choice, attempt_id }),
  cards: () => requestJson<{ cards: SavedCard[] }>(review + "/cards"),
  preview: (source: CardSource) => post<CardPreview>(review + "/cards/preview", source),
  saveCards: (source: CardSource, cards: Card[]) =>
    post<{ cards: SavedCard[] }>(review + "/cards", { ...source, cards }),
  extract: (filename: string, data: string) =>
    post<{ question: string; partial: boolean }>("/api/study/qa/extract", { filename, data }),
  answer: (question: string, resource_id: string) =>
    post<StudyAnswer>("/api/study/qa/answer", { question, resource_id }),
};
