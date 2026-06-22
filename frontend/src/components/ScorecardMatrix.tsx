/* Hygiene scorecard matrix (prototype): sticky repo column, grouped check columns,
   per-cell status glyph; failing-only dims passing cells to 0.12 opacity. */

import { useNavigate } from "react-router-dom";
import type { Scorecard } from "../lib/api";
import { hygColor, viz, type FindingStatus } from "../lib/status";

const CELL = 42;
const REPO_COL = 230;

export function ScorecardMatrix({ data, failingOnly }: { data: Scorecard; failingOnly: boolean }) {
  const navigate = useNavigate();
  const checks = data.checks ?? [];
  const groups = data.groups ?? [];
  const rows = data.rows ?? [];

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "auto", background: "var(--surface)" }}>
      <div style={{ minWidth: "max-content" }}>
        {/* group header */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
          <div style={stickyHead}>Repository</div>
          {groups.map((g) => (
            <div
              key={g.label}
              style={{
                flex: "none",
                width: (g.span ?? 1) * CELL,
                padding: "7px 10px",
                fontSize: 10,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                color: "var(--muted)",
                borderRight: "1px solid var(--border)",
              }}
            >
              {g.label}
            </div>
          ))}
        </div>

        {/* check labels / fail counts */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
          <div style={{ ...stickyCell, padding: "8px 16px", fontSize: 10, color: "var(--muted)" }}>
            {data.repo_count} repos · {checks.length} checks
          </div>
          {checks.map((c) => (
            <div
              key={c.id}
              style={{ flex: "none", width: CELL, padding: "6px 0", textAlign: "center", borderRight: "1px solid var(--border-2)" }}
              title={c.label}
            >
              <div className="mono" style={{ fontSize: 9, fontWeight: 700, color: (c.fail_count ?? 0) ? "var(--fail)" : "var(--muted)" }}>
                {(c.fail_count ?? 0) || "·"}
              </div>
            </div>
          ))}
        </div>

        {/* rows */}
        {rows.map((row) => (
          <div key={row.repo_id} style={{ display: "flex", borderBottom: "1px solid var(--border-2)" }}>
            <div
              onClick={() => navigate(`/repos/${row.repo_id}`)}
              style={{ ...stickyCell, padding: "9px 16px", cursor: "pointer", display: "flex", alignItems: "center", gap: 8 }}
            >
              <span className="mono" style={{ fontSize: 11, fontWeight: 700, color: hygColor(row.hygiene_pct ?? 0), width: 30 }}>
                {row.hygiene_pct}%
              </span>
              <span style={{ fontWeight: 600, fontSize: 12, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {row.repo_id}
              </span>
              <span
                className="mono"
                style={{ fontSize: 8, color: "var(--muted)", border: "1px solid var(--border)", borderRadius: 3, padding: "1px 4px" }}
              >
                {row.connection_badge}
              </span>
            </div>
            {(row.cells ?? []).map((cell, i) => {
              const status = cell as FindingStatus;
              const v = viz(status);
              const dim = failingOnly && status === "pass";
              return (
                <div
                  key={i}
                  style={{
                    flex: "none",
                    width: CELL,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRight: "1px solid var(--border-2)",
                    fontSize: 12,
                    color: v.color,
                    opacity: dim ? 0.12 : 1,
                  }}
                  title={`${checks[i]?.label}: ${v.label}`}
                >
                  {v.glyph}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

const stickyHead: React.CSSProperties = {
  flex: "none",
  width: REPO_COL,
  padding: "7px 16px",
  fontSize: 10,
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  color: "var(--muted)",
  position: "sticky",
  left: 0,
  background: "var(--surface-2)",
  zIndex: 2,
  borderRight: "1px solid var(--border)",
};

const stickyCell: React.CSSProperties = {
  flex: "none",
  width: REPO_COL,
  position: "sticky",
  left: 0,
  background: "var(--surface)",
  zIndex: 1,
  borderRight: "1px solid var(--border)",
};
