import { requestJson } from "./client";
import type { StudyPlan } from "./study";
import type { PlanningPreview } from "./study-planning";

export type GrowthSettings = { timezone: string; minimum_mode: boolean; practice_points?: number; focus_block_points?: number; daily_rewards?: number[] };
export type GrowthDay = { date: string; level: string; completed: number; tasks: number; focus_minutes: number };
export type GrowthState = {
  enabled: boolean; plan_id: string; sunlight: number; plant: string; final_summary?: string; standard_days?: number;
  momentum?: number; settings?: GrowthSettings; days: GrowthDay[];
  available_sunlight?: number; fed_sunlight?: number;
  history?: { request_id: string; task_id: string; old_date: string; new_date: string; minutes: number; active: number }[];
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
export const feedPlant = (id: string, amount: number) =>
  requestJson<GrowthState>(root(id) + "feed", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ amount }) });
export const getLearningDay = (id: string, date: string) => requestJson<Record<string, unknown>>(root(id) + "memory?date=" + date);
export const getLearningWeek = (id: string, date: string) =>
  requestJson<{ body?: string; stats?: Record<string, unknown>; archived?: boolean; final?: Closure }>(root(id) + "weekly?date=" + date);
export const getActivities = () => requestJson<{ events: Activity[] }>("/api/study/growth/events");
export const assignActivity = (event: Activity, plan_id: string|null) =>
  requestJson("/api/study/growth/assign", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: event.kind, event_id: event.id, plan_id }) });
export type FlexPreview = PlanningPreview;
export type SavedPlan = { plan: StudyPlan };

export const getRewardLedger = (id: string) => requestJson<{ entries: { source: string; amount: number; created_at: string }[] }>(root(id) + "ledger");

export type GardenPlant = {
  plan_id: string; title: string; plan_status: string; plant: string; enabled: boolean;
  planted: boolean; closed: boolean; sunlight: number; standard_days: number;
  tasks: number; completed: number; start_date: string; end_date: string;
  summary: string | null; as_of: string; updated_at: string;
};
export type GardenDay = {
  date: string; tasks: number; completed: number; focus_minutes: number;
  attempts: number; correct: number; recalls: number; mastered: number; reward_points: number;
  sources: Record<string, string[]>;
};
export type GardenSummary = {
  plan_id: string; period: string; start_date: string; end_date: string; as_of: string;
  archived: boolean; body: string; stats: Record<string, number | null>; days: GardenDay[];
  final_summary: string | null;
};
export const getStudyGarden = () => requestJson<{ plants: GardenPlant[] }>("/api/study/growth/garden");
export const getGardenSummary = (planId: string, period: string, date: string) =>
  requestJson<GardenSummary>("/api/study/growth/garden-summary?" + new URLSearchParams({ plan_id: planId, period, date }));
