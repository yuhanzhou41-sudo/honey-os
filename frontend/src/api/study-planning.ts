import { apiPath, requestJson } from "./client";
import type { StudyPlan } from "./study";

type Draft = { markdown: string; revision: boolean };
export type PlanningPreview = { plan: StudyPlan; expected_updated_at: string | null };

function json(method: "POST" | "PUT", body: object) {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}
export const planExportUrl = (id: string) => apiPath("/api/study/plans/" + encodeURIComponent(id) + "/markdown");
export const planTemplateUrl = () => apiPath("/api/study/plans/template");
export const previewChatStudyPlan = (draft: Draft) =>
  requestJson<PlanningPreview>("/api/study/chat-plans/preview", json("POST", draft));
export const confirmChatStudyPlan = (draft: Draft, preview: PlanningPreview) =>
  requestJson<{ plan: StudyPlan }>("/api/study/chat-plans/confirm", json("POST", {
    ...draft, plan_id: preview.plan.id, expected_updated_at: preview.expected_updated_at,
  }));
export const listStudyReminders = (plan: string) =>
  requestJson<{ reminders: Record<string, string> }>(`/api/study/plans/${encodeURIComponent(plan)}/reminders`);
export const setStudyReminder = (plan: string, task: string, time: string | null, session_id?: string) =>
  requestJson<{ time: string | null }>(
    `/api/study/plans/${encodeURIComponent(plan)}/tasks/${encodeURIComponent(task)}/reminder`,
    json("PUT", { time, session_id }),
  );
