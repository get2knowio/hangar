/* Sidebar (212px): FLEET nav with active highlight + live urgency badges, and the
   Access footer. Overview badge = CI-fail + critical-alert count (--fail); Scorecard
   badge = repos < 65% hygiene (--warn). (T035, T045, ui-spec §App shell) */

import { useLocation, useNavigate } from "react-router-dom";
import { useConnection } from "./state";
import { logout, useMe, useOverview, useScorecard } from "../lib/api";

export function Sidebar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { active } = useConnection();
  const overview = useOverview(active);
  const scorecard = useScorecard(active, false);
  const me = useMe();

  // Urgency badge from structured summary fields (CI-fail + critical alerts), not a
  // re-parsed display string.
  const summary = overview.data?.summary;
  const overviewBadge = (summary?.ci_failing ?? 0) + (summary?.critical_alerts ?? 0);
  const scorecardBadge = (scorecard.data?.rows ?? []).filter((r) => (r.hygiene_pct ?? 100) < 65).length;

  const items = [
    { path: "/", icon: "◉", label: "Overview", badge: overviewBadge, badgeColor: "var(--fail)" },
    { path: "/scorecard", icon: "▤", label: "Scorecard", badge: scorecardBadge, badgeColor: "var(--warn)" },
    { path: "/catalog", icon: "☰", label: "Catalog & policy", badge: 0, badgeColor: "var(--warn)" },
    { path: "/providers", icon: "⇄", label: "Providers", badge: 0, badgeColor: "var(--warn)" },
  ];

  const isActive = (path: string) =>
    path === "/" ? pathname === "/" || pathname.startsWith("/repos/") : pathname === path;

  const accessMode = me.data?.access_mode ?? "forward-auth";
  const isOidc = accessMode === "oidc";

  return (
    <div
      style={{
        flex: "none",
        width: 212,
        borderRight: "1px solid var(--border)",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        padding: "14px 10px",
      }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "var(--muted)",
          padding: "4px 10px 8px",
        }}
      >
        Fleet
      </div>
      {items.map((it) => {
        const act = isActive(it.path);
        return (
          <div
            key={it.path}
            onClick={() => navigate(it.path)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "8px 10px",
              borderRadius: 6,
              cursor: "pointer",
              marginBottom: 2,
              background: act ? "var(--hover)" : "transparent",
            }}
          >
            <span style={{ width: 15, fontSize: 13, textAlign: "center", color: act ? "var(--fg)" : "var(--muted)" }}>
              {it.icon}
            </span>
            <span style={{ fontSize: 13, fontWeight: act ? 700 : 500, color: act ? "var(--fg)" : "var(--fg-2)", flex: 1 }}>
              {it.label}
            </span>
            {it.badge > 0 && (
              <span
                className="mono"
                style={{
                  fontSize: 10,
                  fontWeight: 600,
                  color: "var(--surface)",
                  background: it.badgeColor,
                  borderRadius: 9,
                  padding: "1px 6px",
                }}
              >
                {it.badge}
              </span>
            )}
          </div>
        );
      })}

      <div style={{ marginTop: "auto", padding: 10, borderTop: "1px solid var(--border-2)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: accessMode === "forward-auth" ? "var(--pass)" : "var(--warn)",
            }}
          />
          <span style={{ fontSize: 11, fontWeight: 600, color: "var(--fg-2)" }}>Access: {accessMode}</span>
        </div>
        {isOidc ? (
          <>
            <div className="mono" style={{ fontSize: 9.5, color: "var(--muted)", lineHeight: 1.5 }}>
              {me.data?.actor ?? "signed in"} · OIDC
            </div>
            <button
              onClick={() => logout()}
              style={{
                marginTop: 8,
                fontSize: 11,
                fontWeight: 600,
                width: "100%",
                padding: "5px 10px",
                borderRadius: 6,
                border: "1px solid var(--border)",
                background: "transparent",
                color: "var(--fg-2)",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              Sign out
            </button>
          </>
        ) : (
          <div className="mono" style={{ fontSize: 9.5, color: "var(--muted)", lineHeight: 1.5 }}>
            {me.data?.user_header ?? "Remote-User"} · fail-closed
            <br />
            behind Traefik
          </div>
        )}
      </div>
    </div>
  );
}
