import { apiPath, fetchWithLocalSessionRecovery, requestJson } from "./client";
import type { StudyCapacityDay, StudyPlan } from "./study";

type Draft = { markdown: string; revision: boolean };
export type PlanningPreview = { plan: StudyPlan; expected_updated_at: string | null; capacity?: StudyCapacityDay[] };

function json(method: "POST" | "PUT", body: object) {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}
export const planExportUrl = (id: string) => apiPath("/api/study/plans/" + encodeURIComponent(id) + "/markdown");
export const planTemplateUrl = (version?: 1 | 2) =>
  apiPath("/api/study/plans/template" + (version ? "?version=" + version : ""));
export const planAuthoringGuideUrl = () => apiPath("/api/study/planning/guide");
export const getStudyPlanningCapabilities = () =>
  requestJson<{ supported_schema_version: 1 | 2; supported_schema_versions: (1 | 2)[] }>("/api/study/planning/capabilities");

export type PlanningRequestInput = {
  objective: string; start_date: string; end_date: string; constraints: string;
  resource_ids: string[]; plan_id?: string;
};
export async function buildPlanningRequest(input: PlanningRequestInput): Promise<string> {
  const response = await fetchWithLocalSessionRecovery(apiPath("/api/study/planning/request"), {
    ...json("POST", input), credentials: "same-origin",
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error || "生成规划请求失败。");
  }
  return response.text();
}
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

export async function confirmManualStudyChange(planId: string, patch: object, taskId?: string) {
  const body = { patch, ...(taskId ? { task_id: taskId } : {}) };
  const preview = await requestJson<PlanningPreview>(
    "/api/study/plans/" + encodeURIComponent(planId) + "/changes/preview", json("POST", body),
  );
  const text = [
    preview.plan.title,
    preview.plan.status ? "状态 " + preview.plan.status : "",
    preview.plan.start_date + " 至 " + preview.plan.end_date,
    ...preview.plan.tasks.map(task => task.title + " · " + task.scheduled_date + " · " + task.planned_minutes + "分钟"),
    ...(preview.capacity ?? []).map(day => day.date + " 合计" + day.total_minutes + "分钟"
      + (day.verified ? " / 上限" + day.limit_minutes + "分钟" : " / 上限未核实")),
  ].join("\n");
  const ending = "status" in patch && ["completed", "archived"].includes(String(patch.status));
  if (!window.confirm(text + (ending ? "\n结束时将保留一句话总结，并清理本计划旧周报正文。" : "") + "\n确认保存本次修改？")) throw new Error("已取消修改。");
  return requestJson<{ plan: StudyPlan }>(
    "/api/study/plans/" + encodeURIComponent(planId) + "/changes/confirm",
    json("POST", { ...body, expected_updated_at: preview.expected_updated_at }),
  );
}
