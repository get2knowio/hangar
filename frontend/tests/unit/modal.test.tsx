/* Regression: the shared Modal is keyboard-complete — labelled dialog role, Escape closes,
   focus lands inside on open, and Tab is trapped within the panel. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Modal } from "../../src/components/Modal";

function setup(onClose = vi.fn()) {
  render(
    <Modal onClose={onClose} label="Add connection">
      <button>first</button>
      <button>last</button>
    </Modal>,
  );
  return onClose;
}

describe("Modal accessibility", () => {
  it("exposes a labelled dialog", () => {
    setup();
    const dialog = screen.getByRole("dialog");
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(dialog.getAttribute("aria-label")).toBe("Add connection");
  });

  it("moves focus to the first focusable element on open", () => {
    setup();
    expect(document.activeElement).toBe(screen.getByText("first"));
  });

  it("closes on Escape", () => {
    const onClose = setup();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("wraps focus from the last element back to the first on Tab", () => {
    setup();
    const last = screen.getByText("last");
    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(screen.getByText("first"));
  });
});
