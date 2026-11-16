import { requestJson } from "./client";

export type QuestionInput = {
  prompt: string; options: string[]; correct: number; explanation: string;
  resource_id: string; excerpt: string;
};
export type Question = Omit<QuestionInput, "correct" | "explanation"> & {
  id: string; source_title: string; latest_correct: number | null;
};
export type Attempt = { id: string; choice: number; correct: number; created_at: string };
export type AnsweredQuestion = Question & { correct?: number; explanation?: string };
type History = { attempts: Attempt[]; question: AnsweredQuestion };
export type Card = { front: string; back: string; excerpt: string };
export type CardSource = { resource_id?: string; question_id?: string };
export type CardPreview = CardSource & { cards: Card[]; source_title: string; partial: boolean };
export type SavedCard = Card & {
  id: string; resource_id: string; question_id: string | null; source_title: string;
};
export type StudyAnswer = {
  answer: string;
  citations: { resource_id: string; source_title: string; excerpt: string }[];
};

const review = "/api/study/review";
const attempts = (id: string) => review + "/questions/" + encodeURIComponent(id) + "/attempts";
function post<T>(path: string, body: object) {
  return requestJson<T>(path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
}
export const studyReview = {
  questions: () => requestJson<{ questions: Question[] }>(review + "/questions"),
  createQuestion: (value: QuestionInput) => post<{ id: string }>(review + "/questions", value),
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
