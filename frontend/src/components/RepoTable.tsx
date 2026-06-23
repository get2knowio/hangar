/* Fleet repo table (prototype): Repository / PRs / CI / Alerts / Release / Hygiene,
   with connection badge and the 🤖 bot-PR flag. Rows drill into the repo. */

import { useNavigate } from "react-router-dom";
import type { Overview } from "../lib/api";
import { ciViz, toneColor } from "../lib/status";
import { ConnectionBadge, HygieneBar } from "./widgets";

const GRID = "2fr 0.7fr 0.6fr 0.7fr 0.7fr 1fr";
type Row = NonNullable<Overview["repos"]>[number];

function releaseColor(days: number | null | undefined): string {
  if (days == null) return "var(--muted)";
  if (days >= 14) return "var(--fail)";
  if (days >= 7) return "var(--warn)";
  return "var(--muted)";
}

export function RepoTable({ repos }: { repos: Row[] }) {
  const navigate = useNavigate();
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", background: "var(--surface)" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: GRID,
          gap: 8,
          padding: "9px 16px",
          fontSize: 10,
          color: "var(--muted)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          fontWeight: 600,
          background: "var(--surface-2)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span>Repository</span>
        <span style={{ textAlign: "right" }}>PRs</span>
        <span style={{ textAlign: "center" }}>CI</span>
        <span style={{ textAlign: "right" }}>Alerts</span>
        <span style={{ textAlign: "right" }}>Release</span>
        <span style={{ textAlign: "right" }}>Hygiene</span>
      </div>
      {repos.map((r) => {
        const ci = ciViz(r.ci ?? "none");
        const rel = r.release_pending_days;
        return (
          <div
            key={r.id}
            onClick={() => navigate(`/repos/${r.connection_id}/${r.id}`)}
            style={{
              display: "grid",
              gridTemplateColumns: GRID,
              gap: 8,
              padding: "11px 16px",
              alignItems: "center",
              borderBottom: "1px solid var(--border-2)",
              cursor: "pointer",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ lineHeight: 1.7 }}>
                <span style={{ fontWeight: 600, fontSize: 13, marginRight: 6 }}>{r.id}</span>
                <ConnectionBadge label={r.connection_badge ?? ""} />
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--muted)",
                  marginTop: 2,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {r.description}
              </div>
            </div>
            <div className="mono" style={{ textAlign: "right", fontSize: 12, whiteSpace: "nowrap" }}>
              <span style={{ color: "var(--fg)" }}>{r.open_prs}</span>
              {(r.dependabot_prs ?? 0) > 0 && (
                <span style={{ color: "var(--warn)", fontSize: 10 }}> · {r.dependabot_prs} 🤖</span>
              )}
            </div>
            <div className="mono" style={{ textAlign: "center", fontSize: 13, color: ci.color }} title={ci.title}>
              {ci.glyph}
            </div>
            <div className="mono" style={{ textAlign: "right", fontSize: 12, color: toneColor((r.alerts_tone as never) ?? "neutral") }}>
              {(r.alerts_total ?? 0) > 0 ? r.alerts_total : "–"}
            </div>
            <div className="mono" style={{ textAlign: "right", fontSize: 12, color: releaseColor(rel) }}>
              {rel != null ? `${rel}d` : "–"}
            </div>
            <HygieneBar pct={r.hygiene_pct ?? 0} />
          </div>
        );
      })}
    </div>
  );
}
