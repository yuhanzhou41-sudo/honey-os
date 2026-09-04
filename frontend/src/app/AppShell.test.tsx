import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { AppShell } from "./AppShell";

function renderShell() {
  return render(
    <MemoryRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<textarea aria-label="消息" />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  Object.defineProperty(window, "visualViewport", {
    configurable: true,
    value: undefined,
  });
});

describe("AppShell mobile keyboard layout", () => {
  it("hides mobile navigation while a text field is focused", () => {
    renderShell();

    fireEvent.focus(screen.getByRole("textbox", { name: "消息" }));

    expect(screen.getAllByRole("navigation", { name: "主要页面" })).toHaveLength(1);
  });

  it("uses the visual viewport height when the software keyboard resizes it", async () => {
    const viewport = Object.assign(new EventTarget(), {
      height: 500,
      offsetTop: 0,
    });
    Object.defineProperty(window, "visualViewport", {
      configurable: true,
      value: viewport,
    });

    renderShell();

    const shell = screen.getByRole("main").parentElement;
    await waitFor(() => expect(shell).toHaveStyle("--honey-viewport-height: 500px"));
  });
});
