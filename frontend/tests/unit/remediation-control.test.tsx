/* RemediationControl resolves the right affordance per finding status. Guards that a
   suppressed check (opted out via .hangar.json) offers no remediation — honest state. */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/app/state", () => ({ useToast: () => ({ show: vi.fn() }) }));
vi.mock("../../src/lib/api", () => ({
  useRemediate: () => ({ mutate: vi.fn(), isPending: false }),
  useMarkMerged: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { RemediationControl } from "../../src/components/RemediationControl";
import type { RepoCheck } from "../../src/lib/api";

function renderCheck(check: Partial<RepoCheck>) {
  render(
    <RemediationControl
      connectionId="c1"
      repoId="r1"
      check={{ id: "dependabot_alerts", label: "Dependabot alerts", ...check } as RepoCheck}
    />,
  );
}

describe("RemediationControl — suppressed", () => {
  it("shows a muted 'Suppressed' note and offers no action button", () => {
    renderCheck({ status: "suppressed" });
    expect(screen.getByText("Suppressed")).toBeInTheDocument();
    // No remediation affordance (no Enable / Open fix PR).
    expect(screen.queryByText(/enable|open fix pr|open in/i)).toBeNull();
  });

  it("still offers a primary action for a plain failing check", () => {
    renderCheck({ status: "fail", primary_action: "Enable", kind: "settings_patch" });
    expect(screen.getByText("Enable")).toBeInTheDocument();
  });
});
