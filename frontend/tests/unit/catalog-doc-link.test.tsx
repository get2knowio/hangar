/* The Catalog & policy page shows a per-rule reference link (Check.doc_url) beside each rule,
   so an operator deciding whether to enable/disable a check can deep-link into what it means.
   The link renders only when the rule carries a doc_url. */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const catalogData = vi.hoisted(() => ({
  current: {
    enabled_count: 2,
    total_count: 2,
    groups: [
      {
        group: "Release",
        checks: [
          {
            id: "release_please",
            label: "release-please configured",
            tier_label: "API · PR",
            enabled: true,
            has_target: false,
            target: null,
            pass_count: 2,
            repo_count: 3,
            doc_url: "https://github.com/googleapis/release-please",
          },
          {
            id: "release_health",
            label: "Release health / commit age",
            tier_label: "Report",
            enabled: true,
            has_target: false,
            target: null,
            pass_count: 3,
            repo_count: 3,
            doc_url: null,
          },
        ],
      },
    ],
  } as unknown,
}));

vi.mock("../../src/lib/api", () => ({
  useCatalog: () => ({ data: catalogData.current, isLoading: false, isError: false, refetch: vi.fn() }),
  usePolicyPatch: () => ({ mutate: vi.fn() }),
}));

import { Catalog } from "../../src/screens/Catalog";

describe("Catalog — per-rule reference link", () => {
  it("links a rule that has a doc_url out to its documentation, in a new tab", () => {
    render(<Catalog />);
    const link = screen.getByRole("link", { name: /release-please configured/i });
    expect(link).toHaveAttribute("href", "https://github.com/googleapis/release-please");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
  });

  it("renders no reference link for a rule without a doc_url", () => {
    render(<Catalog />);
    // Only the one rule with a doc_url should produce a link — the doc_url-less rule adds none.
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});
