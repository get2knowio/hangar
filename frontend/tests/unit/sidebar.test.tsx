/* The sidebar footer shows the running build's version (baked in via vite define), so the
   operator can confirm exactly which image they're on. */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

// Isolate the Sidebar from its data deps; only the version footer is under test.
vi.mock("../../src/lib/api", () => ({
  useMe: () => ({ data: { access_mode: "disabled", user_header: "Remote-User" } }),
  useOverview: () => ({ data: { summary: { ci_failing: 0, critical_alerts: 0 } } }),
  useScorecard: () => ({ data: { rows: [] } }),
  logout: vi.fn(),
}));
vi.mock("../../src/app/state", () => ({ useConnection: () => ({ active: "all" }) }));

import { Sidebar } from "../../src/app/Sidebar";

describe("Sidebar version footer", () => {
  it("shows the running build version", () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    );
    // Matches the version baked in by vite define (e.g. "Hangar v0.3.0"); not hardcoded so a
    // version bump doesn't break the test.
    expect(screen.getByText(/^Hangar v\d+\.\d+\.\d+/)).toBeInTheDocument();
  });
});
