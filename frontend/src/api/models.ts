import { requestJson } from "./client";

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

export function fetchModelOptions(): Promise<ModelOptions> {
  return requestJson<ModelOptions>("/api/model/options");
}

export type GlobalModelSelection = {
  success: boolean;
  provider: string;
  model: string;
};

export function setGlobalDefaultModel(options: {
  provider: string;
  model: string;
}): Promise<GlobalModelSelection> {
  return requestJson<GlobalModelSelection>("/api/model/default", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(options),
  });
}
