/* Status → glyph/color/label and hygiene-color helpers — mirrors the prototype `viz`
   and `hygColor`. Color is the ONLY semantic signal (status-only color). */

import type { components } from "./api-types";

// Derived from the generated OpenAPI contract — no hand-drifted types (Constitution VII).
export type FindingStatus = components["schemas"]["FindingStatus"];
export type Tone = components["schemas"]["Tone"];

export interface Viz {
  color: string;
  glyph: string;
  label: string;
}

export function viz(status: FindingStatus): Viz {
  switch (status) {
    case "pass":
      return { color: "var(--pass)", glyph: "●", label: "Pass" };
    case "fail":
      return { color: "var(--fail)", glyph: "✕", label: "Failing" };
    case "unknown":
      return { color: "var(--unknown)", glyph: "○", label: "Unknown" };
    case "working":
      return { color: "var(--warn)", glyph: "◐", label: "Working" };
    case "pending":
      return { color: "var(--warn)", glyph: "◐", label: "PR open" };
    case "suppressed":
      // Opted out via .hangar.json — muted, distinct from a fail or a pass (honest state).
      return { color: "var(--muted)", glyph: "⊘", label: "Suppressed" };
  }
}

/** Hygiene color thresholds (prototype `hygColor`): ≥85 pass, ≥65 warn, else fail. */
export function hygColor(pct: number): string {
  if (pct >= 85) return "var(--pass)";
  if (pct >= 65) return "var(--warn)";
  return "var(--fail)";
}

export function toneColor(tone: Tone): string {
  switch (tone) {
    case "pass":
      return "var(--pass)";
    case "warn":
      return "var(--warn)";
    case "fail":
      return "var(--fail)";
    case "unknown":
      return "var(--unknown)";
    case "neutral":
      return "var(--fg)";
  }
}

/** CI glyph/color (prototype repo rows). */
export function ciViz(ci: string): { color: string; glyph: string; title: string } {
  if (ci === "pass") return { color: "var(--pass)", glyph: "●", title: "passing" };
  if (ci === "fail") return { color: "var(--fail)", glyph: "●", title: "failing" };
  return { color: "var(--muted)", glyph: "–", title: "no CI" };
}
