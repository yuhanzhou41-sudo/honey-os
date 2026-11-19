import { requestJson } from "./client";
import type { StudyPlan } from "./study";
import type { PlanningPreview } from "./study-planning";

export type GrowthSettings = { timezone: string; minimum_mode: boolean; practice_points?: number; focus_block_points?: number; daily_rewards?: number[] };
export type GrowthDay = { date: string; level: string; completed: number; tasks: number; focus_minutes: number };
export type GrowthState = {
  enabled: boolean; plan_id: string; sunlight: number; plant: string; final_summary?: string; standard_days?: number;
  momentum?: number; settings?: GrowthSettings; days: GrowthDay[];
  history?: { request_id: string; task_id: string; old_date: string; new_date: string; minutes: number; active: number }[];
};
export type SupervisionSettings = {
  enabled: boolean; timezone: string; quiet_start: number; quiet_end: number; remind_hour: number; session_id: string;
};
export type Closure = {
  summary: string; reason: string; expected_updated_at?: string; facts_revision?: string; stats_json: string;
};
export type Activity = { kind: "attempt"|"recall"; id: string; summary?: string; created_at: string; plan_id: string|null };
const root = (id: string) => "/api/study/plans/" + encodeURIComponent(id) + "/growth/";
export function growthAction<T>(id: string, action: string, body: object) {
  return requestJson<T>(root(id) + action, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
export const getGrowth = (id: string) => requestJson<GrowthState>(root(id) + "state");
export const getLearningDay = (id: string, date: string) => requestJson<Record<string, unknown>>(root(id) + "memory?date=" + date);
export const getLearningWeek = (id: string, date: string) =>
  requestJson<{ body?: string; stats?: Record<string, unknown>; archived?: boolean; final?: Closure }>(root(id) + "weekly?date=" + date);
export const getSupervision = () => requestJson<SupervisionSettings>("/api/study/growth/supervision");
export const setSupervision = (settings: SupervisionSettings) =>
  requestJson<SupervisionSettings>("/api/study/growth/supervision", {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(settings),
  });
export const getActivities = () => requestJson<{ events: Activity[] }>("/api/study/growth/events");
export const assignActivity = (event: Activity, plan_id: string|null) =>
  requestJson("/api/study/growth/assign", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: event.kind, event_id: event.id, plan_id }) });
export type FlexPreview = PlanningPreview;
export type SavedPlan = { plan: StudyPlan };

export const getRewardLedger = (id: string) => requestJson<{ entries: { source: string; amount: number; created_at: string }[] }>(root(id) + "ledger");
