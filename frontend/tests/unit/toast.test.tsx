/* Regression: an error toast must read as an error — a failure rendered with the same
   green dot as a success is worse than no toast. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ToastHost, ToastProvider, useToast, type ToastTone } from "../../src/app/state";

function Trigger({ message, tone }: { message: string; tone?: ToastTone }) {
  const { show } = useToast();
  return <button onClick={() => show(message, tone)}>go</button>;
}

function setup(message: string, tone?: ToastTone) {
  render(
    <ToastProvider>
      <Trigger message={message} tone={tone} />
      <ToastHost />
    </ToastProvider>,
  );
  fireEvent.click(screen.getByText("go"));
  return screen.getByRole("status");
}

describe("ToastHost tone", () => {
  it("renders a success toast with the pass accent and polite announcement", () => {
    const toast = setup("Fleet refreshed");
    expect(toast).toHaveTextContent("Fleet refreshed");
    expect(toast.style.borderLeft).toContain("var(--pass)");
    expect(toast.getAttribute("aria-live")).toBe("polite");
  });

  it("renders an error toast with the fail accent and asserts it for screen readers", () => {
    const toast = setup("Fleet refresh failed", "error");
    expect(toast).toHaveTextContent("Fleet refresh failed");
    expect(toast.style.borderLeft).toContain("var(--fail)");
    expect(toast.getAttribute("aria-live")).toBe("assertive");
  });
});
