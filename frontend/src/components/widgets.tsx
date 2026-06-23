/* Token-driven shared primitives reused across screens (T025). */

import { hygColor, toneColor, viz, type FindingStatus, type Tone } from "../lib/status";

export function ConnectionBadge({ label }: { label: string }) {
  return (
    <span
      className="mono"
      style={{
        display: "inline-block",
        fontSize: 9,
        color: "var(--muted)",
        border: "1px solid var(--border)",
        borderRadius: 3,
        padding: "1px 5px",
        verticalAlign: "middle",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}

export function HygieneBar({ pct, width = 46 }: { pct: number; width?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "flex-end", minWidth: 0 }}>
      <div
        style={{
          flex: "1 1 0",
          minWidth: 0,
          maxWidth: width,
          height: 5,
          background: "var(--border)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div style={{ width: `${pct}%`, height: "100%", background: hygColor(pct) }} />
      </div>
      <span
        className="mono"
        style={{ fontSize: 12, fontWeight: 600, color: hygColor(pct), flex: "none", whiteSpace: "nowrap" }}
      >
        {pct}%
      </span>
    </div>
  );
}

export function TierBadge({ label }: { label: string }) {
  return (
    <span
      className="mono"
      style={{
        fontSize: 9,
        color: "var(--muted)",
        border: "1px solid var(--border)",
        borderRadius: 3,
        padding: "1px 6px",
        textTransform: "uppercase",
        letterSpacing: "0.04em",
      }}
    >
      {label}
    </span>
  );
}

export function StatusGlyph({ status, size = 14 }: { status: FindingStatus; size?: number }) {
  const v = viz(status);
  return <span style={{ fontSize: size, color: v.color, width: 16, textAlign: "center" }}>{v.glyph}</span>;
}

export function StatTile({
  label,
  value,
  sub,
  tone,
  subTone,
}: {
  label: string;
  value: string;
  sub: string;
  tone: Tone;
  subTone: Tone;
}) {
  // Color is driven entirely by the structured tone/sub_tone the backend sends — never by
  // matching the tile label or re-parsing the displayed value (Constitution VII).
  const valueColor = toneColor(tone);
  const subColor =
    subTone === "fail" ? "var(--fail)" : subTone === "warn" ? "var(--warn)" : "var(--muted)";
  return (
    <div style={{ padding: "13px 14px", background: "var(--surface)" }}>
      <div
        style={{
          fontSize: 10,
          color: "var(--muted)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          fontWeight: 600,
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </div>
      <div className="mono" style={{ fontSize: 25, fontWeight: 700, marginTop: 4, color: valueColor }}>
        {value}
      </div>
      <div style={{ fontSize: 11, marginTop: 1, color: subColor }}>{sub}</div>
    </div>
  );
}

export { toneColor };
