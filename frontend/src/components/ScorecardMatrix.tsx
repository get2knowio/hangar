/* Hygiene scorecard matrix (prototype): sticky repo column, grouped check columns,
   per-cell status glyph; failing-only dims passing cells to 0.12 opacity. */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useToast } from "../app/state";
import { type BatchTarget, type Scorecard, useRemediateBatch } from "../lib/api";
import { hygColor, viz, type FindingStatus } from "../lib/status";
import { Modal } from "./Modal";

const CELL = 42;
const REPO_COL = 230;

interface BulkPrompt {
  checkId: string;
  label: string;
  targets: BatchTarget[];
}

export function ScorecardMatrix({ data, failingOnly }: { data: Scorecard; failingOnly: boolean }) {
  const navigate = useNavigate();
  const { show } = useToast();
  const batch = useRemediateBatch();
  const [prompt, setPrompt] = useState<BulkPrompt | null>(null);
  const checks = data.checks ?? [];
  const groups = data.groups ?? [];
  const rows = data.rows ?? [];

  // Failing (connection, repo) targets for the check at column `idx`.
  const failingTargets = (idx: number): BatchTarget[] =>
    rows
      .filter((r) => (r.cells ?? [])[idx] === "fail" && r.connection_id && r.repo_id)
      .map((r) => ({ connection_id: r.connection_id as string, repo_id: r.repo_id as string }));

  const runBatch = () => {
    if (!prompt) return;
    batch.mutate(
      { checkId: prompt.checkId, targets: prompt.targets },
      {
        onSuccess: (res) => {
          const s = res.summary ?? {};
          const parts = [
            s.pr_open ? `${s.pr_open} PR${s.pr_open === 1 ? "" : "s"} opened` : "",
            s.fixed ? `${s.fixed} applied` : "",
            s.deep_link ? `${s.deep_link} read-only (deep-link)` : "",
            s.error ? `${s.error} failed` : "",
          ].filter(Boolean);
          show(`${prompt.label}: ${parts.join(" · ") || "no changes"}`);
        },
        onError: () => show(`Bulk remediation failed · ${prompt.label}`, "error"),
        onSettled: () => setPrompt(null),
      },
    );
  };

  return (
    <>
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
          {checks.map((c, i) => {
            const fails = c.fail_count ?? 0;
            const actionable = fails > 0 && !!c.id;
            return (
              <div
                key={c.id}
                onClick={actionable ? () => setPrompt({
                  checkId: c.id as string, label: c.label ?? (c.id as string), targets: failingTargets(i),
                }) : undefined}
                style={{
                  flex: "none", width: CELL, padding: "6px 0", textAlign: "center",
                  borderRight: "1px solid var(--border-2)", cursor: actionable ? "pointer" : "default",
                }}
                title={actionable ? `Remediate "${c.label}" on ${fails} repo${fails === 1 ? "" : "s"}` : c.label}
              >
                <div className="mono" style={{ fontSize: 9, fontWeight: 700, color: fails ? "var(--fail)" : "var(--muted)" }}>
                  {fails || "·"}
                </div>
              </div>
            );
          })}
        </div>

        {/* rows */}
        {rows.map((row) => (
          <div key={row.repo_id} style={{ display: "flex", borderBottom: "1px solid var(--border-2)" }}>
            <div
              onClick={() => navigate(`/repos/${row.connection_id}/${row.repo_id}`)}
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
    {prompt && (
      <Modal
        onClose={() => {
          if (!batch.isPending) setPrompt(null);
        }}
        label={`Remediate ${prompt.label} across failing repos`}
        width={380}
      >
        <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 6 }}>
          Remediate “{prompt.label}”
        </div>
        <p style={{ fontSize: 13, color: "var(--muted)", margin: "0 0 16px" }}>
          {prompt.targets.length === 0
            ? "No failing repos for this check."
            : `Opens a fix PR on each of ${prompt.targets.length} failing repo${prompt.targets.length === 1 ? "" : "s"} (read-only connections collapse to a deep-link). This is idempotent — an existing Hangar PR is reused, not duplicated.`}
        </p>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button
            onClick={() => setPrompt(null)}
            disabled={batch.isPending}
            style={{
              fontSize: 12, fontWeight: 600, padding: "7px 13px", borderRadius: 6,
              border: "1px solid var(--border)", background: "transparent", color: "var(--fg-2)",
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={runBatch}
            disabled={batch.isPending || prompt.targets.length === 0}
            style={{
              fontSize: 12, fontWeight: 600, padding: "7px 13px", borderRadius: 6,
              border: "1px solid var(--fg)", background: "var(--fg)", color: "var(--bg)",
              cursor: batch.isPending || prompt.targets.length === 0 ? "default" : "pointer",
              opacity: prompt.targets.length === 0 ? 0.5 : 1,
            }}
          >
            {batch.isPending ? "Working…" : `Remediate ${prompt.targets.length}`}
          </button>
        </div>
      </Modal>
    )}
    </>
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
