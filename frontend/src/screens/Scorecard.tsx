/* Hygiene scorecard (/scorecard) — matrix + roll-up, top-drift chips, failing-only
   toggle (FR-005–FR-007). */

import { useState } from "react";
import { ErrorState } from "../components/ErrorState";
import { ScorecardMatrix } from "../components/ScorecardMatrix";
import { useConnection } from "../app/state";
import { useProviders, useScorecard } from "../lib/api";

export function Scorecard() {
  const { active } = useConnection();
  const [failingOnly, setFailingOnly] = useState(false);
  const { data, isLoading, isError, error, refetch } = useScorecard(active, failingOnly);
  const providers = useProviders();

  const scopeLabel =
    active === "all"
      ? "all connections"
      : (providers.data?.connections?.find((c) => c.id === active)?.label ?? active);

  if (isError) {
    return <ErrorState title="Couldn't load the scorecard" error={error} onRetry={refetch} />;
  }
  if (isLoading || !data) {
    return <div style={{ padding: "24px 28px", color: "var(--muted)" }}>Loading scorecard…</div>;
  }

  return (
    <div style={{ padding: "24px 28px" }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>Hygiene scorecard</h1>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>
          {data.compliance_pct}% fleet compliance · {data.clear_count}/{data.repo_count} clear
        </span>
      </div>
      <p style={{ margin: "0 0 16px", fontSize: 13, color: "var(--muted)" }}>
        Active policy evaluated against every repo in {scopeLabel}.
      </p>

      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 16 }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Top drift
        </span>
        {(data.rollup ?? []).map((ro) => (
          <span
            key={ro.label}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 12,
              background: "var(--fail-bg)",
              color: "var(--fail)",
              borderRadius: 14,
              padding: "3px 11px",
              fontWeight: 500,
            }}
          >
            <span className="mono" style={{ fontWeight: 700 }}>
              {ro.count}
            </span>{" "}
            {ro.label}
          </span>
        ))}
        <button
          onClick={() => setFailingOnly((f) => !f)}
          aria-pressed={failingOnly}
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: 7,
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 600,
            color: "var(--fg-2)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            padding: "5px 11px",
            background: failingOnly ? "var(--hover)" : "var(--surface)",
            fontFamily: "inherit",
          }}
        >
          <span style={{ width: 8, height: 8, borderRadius: 2, background: failingOnly ? "var(--fail)" : "var(--border)" }} />
          {failingOnly ? "Failing only" : "All cells"}
        </button>
      </div>

      <ScorecardMatrix data={data} failingOnly={failingOnly} />

      <div style={{ display: "flex", gap: 18, marginTop: 12, fontSize: 11, color: "var(--muted)", flexWrap: "wrap" }}>
        <span>
          <span style={{ color: "var(--pass)" }}>●</span> pass
        </span>
        <span>
          <span style={{ color: "var(--fail)" }}>✕</span> fail
        </span>
        <span>
          <span style={{ color: "var(--unknown)" }}>○</span> unknown (scope)
        </span>
        <span>
          <span style={{ color: "var(--warn)" }}>◐</span> remediation in flight
        </span>
        <span>Click a repo to drill in →</span>
      </div>
    </div>
  );
}
