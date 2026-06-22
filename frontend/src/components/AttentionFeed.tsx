/* Attention feed (prototype): left-border tone, tag + repo + title, urgency-ordered. */

import { useNavigate } from "react-router-dom";
import type { Overview } from "../lib/api";
import { toneColor } from "../lib/status";

type Item = NonNullable<Overview["feed"]>[number];

export function AttentionFeed({ feed }: { feed: Item[] }) {
  const navigate = useNavigate();
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", overflow: "hidden" }}>
      <div
        style={{
          padding: "11px 16px",
          fontSize: 11,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          color: "var(--muted)",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface-2)",
        }}
      >
        Needs attention · by urgency
      </div>
      {feed.map((f, i) => {
        const color = toneColor((f.tone as never) ?? "neutral");
        return (
          <div
            key={`${f.repo_id}-${i}`}
            onClick={() => navigate(`/repos/${f.repo_id}`)}
            style={{
              padding: "11px 16px",
              borderBottom: "1px solid var(--border-2)",
              borderLeft: `3px solid ${color}`,
              cursor: "pointer",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color }}>
                {f.tag}
              </span>
              <span className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>
                {f.repo_id}
              </span>
            </div>
            <div style={{ fontSize: 13, color: "var(--fg)", marginTop: 3 }}>{f.title}</div>
          </div>
        );
      })}
      <div style={{ padding: "10px 16px", fontSize: 11, color: "var(--muted)" }}>
        Sorted: critical → CI → release → alerts → bot PRs
      </div>
    </div>
  );
}
