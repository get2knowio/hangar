/* Topbar (52px): logo + breadcrumb, connection switcher, synced indicator, theme toggle. */

import { useLocation } from "react-router-dom";
import { ConnSwitcher } from "../components/ConnSwitcher";
import { useOverview, useSyncFleet } from "../lib/api";
import { useConnection, useTheme, useToast } from "./state";

const TITLES: Record<string, string> = {
  "/": "Fleet overview",
  "/scorecard": "Hygiene scorecard",
  "/catalog": "Catalog & policy",
  "/providers": "Providers & access",
};

function titleFor(path: string): string {
  if (path.startsWith("/repos/")) return "Repository";
  return TITLES[path] ?? "Fleet overview";
}

export function Topbar() {
  const { pathname } = useLocation();
  const { theme, toggle } = useTheme();
  const { active } = useConnection();
  const { show } = useToast();
  const syncFleet = useSyncFleet();

  // Honest, single-sourced staleness: /fleet/overview computes summary.synced as the most
  // recent successful sync across the scoped connections (or "never" during an outage) — no
  // hardcoded value. Reuses the query the Sidebar already loads, so it costs nothing extra.
  const overview = useOverview(active);
  const synced = overview.data?.summary?.synced ?? "—";

  return (
    <div
      style={{
        flex: "none",
        height: 52,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 18px",
        borderBottom: "1px solid var(--border)",
        background: "var(--surface)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <div style={{ width: 18, height: 18, background: "var(--fg)", borderRadius: 4, position: "relative" }}>
            <div
              style={{
                position: "absolute",
                inset: "5px 4px 4px 4px",
                border: "1.5px solid var(--surface)",
                borderBottom: "none",
                borderRadius: "2px 2px 0 0",
              }}
            />
          </div>
          <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>Hangar</span>
        </div>
        <span style={{ color: "var(--border)" }}>/</span>
        <span style={{ fontSize: 13, color: "var(--fg-2)", fontWeight: 500 }}>{titleFor(pathname)}</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <ConnSwitcher />
        <span style={{ fontSize: 11, color: "var(--muted)" }}>synced {synced}</span>
        <button
          onClick={() =>
            syncFleet.mutate(undefined, {
              onSuccess: () => show("Fleet refreshed"),
              onError: () => show("Fleet refresh failed", "error"),
            })
          }
          disabled={syncFleet.isPending}
          title="Re-interrogate every connection now"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 10px",
            border: "1px solid var(--border)",
            borderRadius: 6,
            cursor: syncFleet.isPending ? "default" : "pointer",
            fontSize: 11,
            fontWeight: 600,
            color: "var(--fg-2)",
            background: "transparent",
            fontFamily: "inherit",
            opacity: syncFleet.isPending ? 0.6 : 1,
          }}
        >
          <span
            style={{
              display: "inline-block",
              animation: syncFleet.isPending ? "hgspin .8s linear infinite" : undefined,
            }}
          >
            ↻
          </span>
          {syncFleet.isPending ? "Refreshing…" : "Refresh"}
        </button>
        <div
          onClick={toggle}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 10px",
            border: "1px solid var(--border)",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 11,
            fontWeight: 600,
            color: "var(--fg-2)",
          }}
        >
          {theme === "dark" ? "☀ Light" : "☾ Dark"}
        </div>
      </div>
    </div>
  );
}
