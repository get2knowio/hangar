import { describe, expect, it } from "vitest";
import { ciViz, hygColor, toneColor, viz } from "../../src/lib/status";

describe("viz", () => {
  it("maps each status to the prototype glyph/label", () => {
    expect(viz("pass")).toMatchObject({ glyph: "●", label: "Pass", color: "var(--pass)" });
    expect(viz("fail")).toMatchObject({ glyph: "✕", color: "var(--fail)" });
    expect(viz("unknown")).toMatchObject({ glyph: "○", color: "var(--unknown)" });
    expect(viz("working")).toMatchObject({ glyph: "◐", label: "Working", color: "var(--warn)" });
    expect(viz("pending")).toMatchObject({ glyph: "◐", label: "PR open", color: "var(--warn)" });
  });
});

describe("hygColor thresholds (≥85 pass, ≥65 warn, else fail)", () => {
  it("classifies", () => {
    expect(hygColor(100)).toBe("var(--pass)");
    expect(hygColor(85)).toBe("var(--pass)");
    expect(hygColor(84)).toBe("var(--warn)");
    expect(hygColor(65)).toBe("var(--warn)");
    expect(hygColor(64)).toBe("var(--fail)");
    expect(hygColor(0)).toBe("var(--fail)");
  });
});

describe("ciViz", () => {
  it("colors CI states", () => {
    expect(ciViz("pass").color).toBe("var(--pass)");
    expect(ciViz("fail").color).toBe("var(--fail)");
    expect(ciViz("none")).toMatchObject({ glyph: "–", color: "var(--muted)" });
  });
});

describe("toneColor", () => {
  it("maps tones to tokens", () => {
    expect(toneColor("fail")).toBe("var(--fail)");
    expect(toneColor("warn")).toBe("var(--warn)");
    expect(toneColor("neutral")).toBe("var(--fg)");
  });
});
