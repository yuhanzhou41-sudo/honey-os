import { requestJson } from "./client";

export type Imprint = {
  status: string;
  axis: string | null;
  label: string | null;
  formed_at: string | null;
} | null;

export type GraphMemory = {
  kind: string;
  created_at: string;
  content: string;
  source_session_id: string;
  imprint: Imprint;
};

export type GraphEvidence = {
  ref: string;
  relation: string;
  occurred_at: string | null;
  source_revision: string | null;
  memory: GraphMemory | null;
};

export type LabelVersion = {
  revision: number;
  body: string;
  state: string;
  grade: string;
  actor: string;
  created_at: string | null;
};

export type GraphLabel = {
  id: string;
  category_id: string;
  scope_key: string;
  canonical_key: string;
  text: string;
  state: string;
  grade: string;
  revision: number;
  created_at: string | null;
  updated_at: string | null;
  suppressed: boolean;
  evidence: GraphEvidence[];
  versions?: LabelVersion[];
};

export type GraphResponse = {
  labels: GraphLabel[];
  total: number;
  owner: string;
};

export function fetchUnderstandingGraph(params?: {
  lane?: string;
  namespace?: string;
  limit?: number;
  offset?: number;
}): Promise<GraphResponse> {
  const q = new URLSearchParams();
  if (params?.lane) q.set("lane", params.lane);
  if (params?.namespace) q.set("namespace", params.namespace);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  const suffix = q.toString();
  return requestJson<GraphResponse>(
    `/api/understanding/graph${suffix ? `?${suffix}` : ""}`,
  );
}

export function fetchUnderstandingLabel(labelId: string): Promise<GraphLabel> {
  return requestJson<GraphLabel>(
    `/api/understanding/labels/${encodeURIComponent(labelId)}`,
  );
}

export function suppressUnderstandingLabel(labelId: string): Promise<{ ok: boolean }> {
  return requestJson(`/api/understanding/labels/${encodeURIComponent(labelId)}/suppress`, {
    method: "POST",
  });
}

export function detachUnderstandingEvidence(
  labelId: string,
  ref: string,
): Promise<{ ok: boolean; removed: number; recomputed?: { changed: boolean; state?: string; grade?: string } }> {
  return requestJson(
    `/api/understanding/labels/${encodeURIComponent(labelId)}/evidence?ref=${encodeURIComponent(ref)}`,
    { method: "DELETE" },
  );
}
