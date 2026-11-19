import { requestJson } from "./client";

export type CampusExamRecord = {
  id: string;
  source: string;
  batch_key: string;
  course: string;
  exam_date: string;
  arrangement: string;
  location: string;
  captured_at: string;
};

export type CampusExams = {
  records: CampusExamRecord[];
  source: string | null;
  captured_at: string | null;
  last_success_at: string | null;
  row_count: number;
  has_data: boolean;
  stale: boolean;
  needs_capture: boolean;
  result?: string;
  action?: string;
  imported?: number;
  message?: string;
};

export const getCampusExams = () =>
  requestJson<{ exams: CampusExams }>("/api/campus/exams");

export const refreshCampusExams = () =>
  requestJson<{ exams: CampusExams }>("/api/campus/exams/refresh", { method: "POST" });
