import { describe, expect, it } from "vitest";

import { fetchModelOptions, setGlobalDefaultModel } from "./models";

describe("shared model inventory API", () => {
  it("exports the shared model-options reader", () => {
    expect(typeof fetchModelOptions).toBe("function");
    expect(typeof setGlobalDefaultModel).toBe("function");
  });
});
