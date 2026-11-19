import { apiPath, fetchWithLocalSessionRecovery } from "./client";

export type ModelProviderOption = {
  slug: string;
  name: string;
  authenticated: boolean;
  models: string[];
  is_current?: boolean;
  warning?: string;
};

export type ModelOptions = {
  providers: ModelProviderOption[];
  model?: string;
  provider?: string;
};

async function modelOptionsError(response: Response): Promise<Error> {
  let detail = "";
  try {
    detail = await response.text();
  } catch {
    detail = "";
  }
  return new Error(detail || `Model options request failed (${response.status})`);
}

export async function fetchModelOptions(): Promise<ModelOptions> {
  const response = await fetchWithLocalSessionRecovery(
    apiPath("/api/model/options"),
    {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    },
  );
  if (!response.ok) throw await modelOptionsError(response);
  return response.json() as Promise<ModelOptions>;
}

export type GlobalModelSelection = {
  success: boolean;
  provider: string;
  model: string;
};

export async function setGlobalDefaultModel(options: {
  provider: string;
  model: string;
}): Promise<GlobalModelSelection> {
  const response = await fetchWithLocalSessionRecovery(
    apiPath("/api/model/default"),
    {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(options),
    },
  );
  if (!response.ok) throw await modelOptionsError(response);
  return response.json() as Promise<GlobalModelSelection>;
}

