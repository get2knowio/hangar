/* Repo drill-down (/repos/:id) — header, activity strip, grouped policy checks with the
   remediation control + remediation-pending overlay (Story 3; FR-005a, FR-011–FR-018). */

import { useNavigate, useParams } from "react-router-dom";
import { RemediationControl } from "../components/RemediationControl";
import { TierBadge } from "../components/widgets";
import { useRepoDetail } from "../lib/api";
import { ciViz, hygColor, viz, type FindingStatus } from "../lib/status";

const ALERT_COLOR: Record<string, { color: string; bg: string }> = {
  critical: { color: "var(--fail)", bg: "var(--fail-bg)" },
  high: { color: "var(--warn)", bg: "var(--warn-bg)" },
  moderate: { color: "var(--fg-2)", bg: "var(--surface-2)" },
  low: { color: "var(--muted)", bg: "var(--surface-2)" },
};

export function RepoDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, isLoading } = useRepoDetail(id);

  if (isLoading || !data) {
    return <div style={{ padding: "24px 28px", color: "var(--muted)" }}>Loading repo…</div>;
  }

  const ci = ciViz(data.ci ?? "none");
  const prs = data.pull_requests ?? [];
  const alerts = data.alerts ?? [];

  return (
    <div style={{ padding: "24px 28px", maxWidth: 1000 }}>
      <div
        onClick={() => navigate(-1)}
        style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--muted)", cursor: "pointer", marginBottom: 14 }}
      >
        ← Back
      </div>

      <div style={{ display: "flex", alignItems: "flex-start", gap: 16, marginBottom: 22 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <h1 className="mono" style={{ margin: 0, fontSize: 23, fontWeight: 700, letterSpacing: "-0.02em" }}>
              {data.id}
            </h1>
            <span
              className="mono"
              style={{ fontSize: 10, color: "var(--muted)", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 8px" }}
            >
              {data.connection_label}
            </span>
            {data.read_only && (
              <span style={{ fontSize: 10, fontWeight: 600, color: "var(--warn)", background: "var(--warn-bg)", borderRadius: 4, padding: "2px 8px" }}>
                read-only · deep-link only
              </span>
            )}
          </div>
          <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--muted)" }}>{data.description}</p>
        </div>
        <div style={{ flex: "none", textAlign: "right" }}>
          <div className="mono" style={{ fontSize: 34, fontWeight: 700, lineHeight: 1, color: hygColor(data.hygiene_pct ?? 0) }}>
            {data.hygiene_pct}%
          </div>
          <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginTop: 3 }}>
            hygiene · {data.pass_count}
          </div>
        </div>
      </div>

      {/* activity strip */}
      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 16, marginBottom: 24, alignItems: "start" }}>
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", overflow: "hidden" }}>
          <div
            style={{
              padding: "10px 15px",
              fontSize: 11,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              color: "var(--muted)",
              borderBottom: "1px solid var(--border)",
              background: "var(--surface-2)",
              display: "flex",
              justifyContent: "space-between",
            }}
          >
            <span>Open pull requests</span>
            <span className="mono" style={{ color: "var(--fg-2)" }}>
              {data.open_prs}
            </span>
          </div>
          {prs.map((pr, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 15px", borderBottom: "1px solid var(--border-2)" }}>
              <span style={{ fontSize: 11, width: 14, textAlign: "center", color: pr.kind === "dependabot" ? "var(--warn)" : "var(--fg-2)" }}>
                {pr.kind === "dependabot" ? "⚙" : "↗"}
              </span>
              <span style={{ flex: 1, fontSize: 13, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{pr.title}</span>
              <span style={{ fontSize: 11, fontWeight: 600, color: pr.status === "ready" ? "var(--pass)" : pr.status?.startsWith("cooldown") ? "var(--warn)" : "var(--fg-2)" }}>
                {pr.status}
              </span>
              <span className="mono" style={{ fontSize: 10, color: "var(--muted)" }}>
                {pr.age}
              </span>
            </div>
          ))}
          {prs.length === 0 && <div style={{ padding: "14px 15px", fontSize: 12, color: "var(--muted)" }}>No open pull requests.</div>}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", padding: "13px 15px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--muted)", marginBottom: 8 }}>
              CI · default branch
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
              <span style={{ fontSize: 14, color: ci.color }}>{ci.glyph}</span>
              <span style={{ fontSize: 14, fontWeight: 600, color: ci.color }}>
                {data.ci === "pass" ? "Passing" : data.ci === "fail" ? "Failing" : "No CI configured"}
              </span>
            </div>
          </div>
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", padding: "13px 15px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--muted)", marginBottom: 8 }}>
              Security alerts
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {alerts.map((al) => {
                const c = ALERT_COLOR[al.severity ?? "low"];
                return (
                  <span key={al.severity} className="mono" style={{ fontSize: 12, fontWeight: 600, color: c.color, background: c.bg, borderRadius: 5, padding: "3px 9px" }}>
                    {al.count} {al.severity}
                  </span>
                );
              })}
              {alerts.length === 0 && <span style={{ fontSize: 12, color: "var(--pass)" }}>No open alerts</span>}
            </div>
          </div>
        </div>
      </div>

      {/* policy checks & remediation */}
      <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)", marginBottom: 10 }}>
        Policy checks & remediation
      </div>
      {(data.check_groups ?? []).map((grp) => (
        <div key={grp.group} style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-2)", marginBottom: 7 }}>{grp.group}</div>
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", background: "var(--surface)" }}>
            {(grp.checks ?? []).map((c) => {
              const v = viz((c.status as FindingStatus) ?? "fail");
              return (
                <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 13, padding: "12px 16px", borderBottom: "1px solid var(--border-2)" }}>
                  <span style={{ fontSize: 14, width: 16, textAlign: "center", color: v.color, flex: "none" }}>{v.glyph}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{c.label}</span>
                      <TierBadge label={c.tier_label ?? ""} />
                    </div>
                    <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{c.evidence}</div>
                  </div>
                  <RemediationControl repoId={data.id!} check={c} />
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
