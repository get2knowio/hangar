import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HygieneBar, StatTile, StatusGlyph } from "../../src/components/widgets";

describe("widgets", () => {
  it("StatTile renders label/value/sub", () => {
    render(<StatTile label="Compliance" value="85%" sub="fleet avg" tone="pass" />);
    expect(screen.getByText("Compliance")).toBeInTheDocument();
    expect(screen.getByText("85%")).toBeInTheDocument();
    expect(screen.getByText("fleet avg")).toBeInTheDocument();
  });

  it("HygieneBar shows the percent", () => {
    render(<HygieneBar pct={74} />);
    expect(screen.getByText("74%")).toBeInTheDocument();
  });

  it("StatusGlyph renders the failing glyph", () => {
    render(<StatusGlyph status="fail" />);
    expect(screen.getByText("✕")).toBeInTheDocument();
  });
});
