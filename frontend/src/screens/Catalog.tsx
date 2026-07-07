/* Check catalog & policy (/catalog) — grouped checks, enable toggles, tier badges,
   cooldown target, per-check pass-rate bar. Edits recompute the scorecard live
   (Constitution IV, SC-005). */

import { ErrorState } from "../components/ErrorState";
import { hygColor } from "../lib/status";
import { useCatalog, usePolicyPatch } from "../lib/api";

export function Catalog() {
  const { data, isLoading, isError, error, refetch } = useCatalog();
  const patch = usePolicyPatch();

  if (isError) {
    return <ErrorState title="Couldn't load the catalog" error={error} onRetry={refetch} />;
  }
  if (isLoading || !data) {
    return <div style={{ padding: "24px 28px", color: "var(--muted)" }}>Loading catalog…</div>;
  }

  return (
    <div style={{ padding: "24px 28px", maxWidth: 920 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>Check catalog & policy</h1>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>
          {data.enabled_count} of {data.total_count} checks active
        </span>
      </div>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: "var(--muted)" }}>
        The catalog is data, not UI. Toggle a check into the fleet-wide policy or set its target — the
        scorecard recomputes live.
      </p>

      {(data.groups ?? []).map((grp) => (
        <div key={grp.group} style={{ marginBottom: 22 }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              color: "var(--muted)",
              marginBottom: 8,
            }}
          >
            {grp.group}
          </div>
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", background: "var(--surface)" }}>
            {(grp.checks ?? []).map((c) => {
              const pct = c.repo_count ? Math.round(((c.pass_count ?? 0) / c.repo_count) * 100) : 100;
              return (
                <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 14, padding: "12px 16px", borderBottom: "1px solid var(--border-2)" }}>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={c.enabled}
                    aria-label={`${c.enabled ? "Disable" : "Enable"} ${c.label}`}
                    onClick={() => patch.mutate({ check_id: c.id!, enabled: !c.enabled })}
                    style={{
                      flex: "none",
                      width: 34,
                      height: 19,
                      borderRadius: 11,
                      border: "none",
                      background: c.enabled ? "var(--fg)" : "var(--border)",
                      display: "flex",
                      alignItems: "center",
                      padding: 2,
                      cursor: "pointer",
                      justifyContent: c.enabled ? "flex-end" : "flex-start",
                      transition: "background .15s",
                    }}
                  >
                    <div style={{ width: 15, height: 15, borderRadius: "50%", background: "#fff", boxShadow: "0 1px 2px rgba(0,0,0,.3)" }} />
                  </button>
                  <div style={{ flex: 1, minWidth: 0, opacity: c.enabled ? 1 : 0.45 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                      <span style={{ fontWeight: 600, fontSize: 13 }}>{c.label}</span>
                      {c.doc_url && (
                        <a
                          href={c.doc_url}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`About the ${c.label} rule (opens documentation)`}
                          title={`About “${c.label}” — opens documentation`}
                          style={{ display: "inline-flex", color: "var(--muted)", flex: "none" }}
                        >
                          <svg
                            width="12" height="12" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
                            strokeLinejoin="round" aria-hidden="true"
                          >
                            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                            <polyline points="15 3 21 3 21 9" />
                            <line x1="10" y1="14" x2="21" y2="3" />
                          </svg>
                        </a>
                      )}
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
                        {c.tier_label}
                      </span>
                    </div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                      {c.id}
                    </div>
                  </div>
                  {c.has_target && (
                    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>target</span>
                      <input
                        type="number"
                        min={0}
                        max={90}
                        defaultValue={c.target ?? 0}
                        onChange={(e) =>
                          patch.mutate({ check_id: c.id!, params: { target: Math.max(0, parseInt(e.target.value) || 0) } })
                        }
                        style={{
                          width: 52,
                          padding: "5px 7px",
                          border: "1px solid var(--border)",
                          borderRadius: 5,
                          background: "var(--surface-2)",
                          color: "var(--fg)",
                          fontSize: 12,
                          textAlign: "center",
                        }}
                      />
                      <span style={{ fontSize: 11, color: "var(--muted)" }}>days</span>
                    </div>
                  )}
                  <div style={{ flex: "none", width: 120, textAlign: "right" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7, justifyContent: "flex-end" }}>
                      <div style={{ width: 44, height: 5, background: "var(--border)", borderRadius: 3, overflow: "hidden" }}>
                        <div style={{ width: `${pct}%`, height: "100%", background: hygColor(pct) }} />
                      </div>
                      <span className="mono" style={{ fontSize: 11, color: "var(--fg-2)", width: 42, textAlign: "right" }}>
                        {c.pass_count}/{c.repo_count}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
