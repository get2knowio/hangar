/* Regression: the Topbar "synced" indicator must reflect the real fleet-wide value from
   /fleet/overview (summary.synced) — never a hardcoded string — and fall back to "—" (not a
   fabricated time) while that value is unknown. Guards the honest-state fix. */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

// Isolate the Topbar from its data/context deps so the test targets the synced wiring only.
const useOverview = vi.fn();
vi.mock("../../src/lib/api", () => ({
  useOverview: (c: string) => useOverview(c),
  useSyncFleet: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("../../src/app/state", () => ({
  useConnection: () => ({ active: "all" }),
  useTheme: () => ({ theme: "dark", toggle: vi.fn() }),
  useToast: () => ({ show: vi.fn() }),
}));
vi.mock("../../src/components/ConnSwitcher", () => ({ ConnSwitcher: () => null }));

import { Topbar } from "../../src/app/Topbar";

const renderTopbar = () =>
  render(
    <MemoryRouter>
      <Topbar />
    </MemoryRouter>,
  );

describe("Topbar synced indicator", () => {
  it("shows the real overview summary.synced value", () => {
    useOverview.mockReturnValue({ data: { summary: { synced: "3m ago" } } });
    renderTopbar();
    expect(screen.getByText("synced 3m ago")).toBeInTheDocument();
  });

  it("reports 'never' honestly when nothing has synced", () => {
    useOverview.mockReturnValue({ data: { summary: { synced: "never" } } });
    renderTopbar();
    expect(screen.getByText("synced never")).toBeInTheDocument();
  });

  it("falls back to '—' (not a fabricated time) while the value is unknown", () => {
    useOverview.mockReturnValue({ data: undefined });
    renderTopbar();
    expect(screen.getByText("synced —")).toBeInTheDocument();
    expect(screen.queryByText(/synced \d+m ago/)).not.toBeInTheDocument();
  });

  it("makes the top-left brand a link back to the overview (/)", () => {
    useOverview.mockReturnValue({ data: undefined });
    renderTopbar();
    expect(screen.getByRole("link", { name: /hangar/i })).toHaveAttribute("href", "/");
  });
});
