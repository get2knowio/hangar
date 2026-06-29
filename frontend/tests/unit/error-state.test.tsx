/* Regression: a failed data load shows an actionable error panel (not a blank/forever-
   loading screen), with copy matched to what actually went wrong, and a working retry. */

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorState } from "../../src/components/ErrorState";

describe("ErrorState", () => {
  it("tells an expired-session user to reload on a 401", () => {
    render(<ErrorState title="Couldn't load the fleet" error={{ status: 401 }} />);
    expect(screen.getByText("Couldn't load the fleet")).toBeInTheDocument();
    expect(screen.getByText(/session has ended/i)).toBeInTheDocument();
  });

  it("frames a 5xx as a temporary server error", () => {
    render(<ErrorState title="x" error={{ status: 503 }} />);
    expect(screen.getByText(/server returned an error/i)).toBeInTheDocument();
  });

  it("falls back to a connectivity message when there is no status", () => {
    render(<ErrorState title="x" error={new Error("network down")} />);
    expect(screen.getByText(/couldn't reach the server/i)).toBeInTheDocument();
  });

  it("invokes onRetry when 'Try again' is clicked", () => {
    const onRetry = vi.fn();
    render(<ErrorState title="x" error={{ status: 500 }} onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("omits the retry button when no handler is given", () => {
    render(<ErrorState title="x" error={{ status: 500 }} />);
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
  });
});
