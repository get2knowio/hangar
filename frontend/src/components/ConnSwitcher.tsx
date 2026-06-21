/* Topbar connection switcher (prototype): All vs per-connection, re-scopes every screen
   via the shared connection filter. Dot color = writable (pass) vs read-only (warn). */

import { useState } from "react";
import { useConnection } from "../app/state";
import { useProviders } from "../lib/api";

export function ConnSwitcher() {
  const [open, setOpen] = useState(false);
  const { active, setActive } = useConnection();
  const { data } = useProviders();
  const connections = data?.connections ?? [];
  const totalRepos = connections.reduce((a, c) => a + (c.repos ?? 0), 0);

  const activeConn = connections.find((c) => c.id === active);
  const label = active === "all" ? "All connections" : (activeConn?.label ?? active);

  const options = [
    { id: "all", label: "All connections", meta: `${totalRepos} repos`, dot: "var(--pass)" },
    ...connections.map((c) => ({
      id: c.id!,
      label: c.label!,
      meta: (c.scope ?? "").split("· ")[1] ?? "",
      dot: c.writes ? "var(--pass)" : "var(--warn)",
    })),
  ];

  return (
    <div style={{ position: "relative" }}>
      <div
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "5px 10px",
          border: "1px solid var(--border)",
          borderRadius: 6,
          cursor: "pointer",
          background: "var(--surface)",
        }}
      >
        <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--pass)" }} />
        <span className="mono" style={{ fontSize: 11, fontWeight: 600, color: "var(--fg)" }}>
          {label}
        </span>
        <span style={{ color: "var(--muted)", fontSize: 10 }}>▾</span>
      </div>
      {open && (
        <div
          style={{
            position: "absolute",
            top: 38,
            right: 0,
            width: 248,
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            boxShadow: "0 8px 28px rgba(0,0,0,.14)",
            padding: 5,
            zIndex: 50,
            animation: "hgfade .12s ease",
          }}
        >
          {options.map((opt) => (
            <div
              key={opt.id}
              onClick={() => {
                setActive(opt.id);
                setOpen(false);
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 9,
                padding: "8px 9px",
                borderRadius: 5,
                cursor: "pointer",
              }}
            >
              <span style={{ width: 13, textAlign: "center", color: "var(--pass)", fontSize: 11 }}>
                {active === opt.id ? "✓" : ""}
              </span>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: opt.dot, flex: "none" }} />
              <span className="mono" style={{ fontSize: 11.5, fontWeight: 600, flex: 1 }}>
                {opt.label}
              </span>
              <span style={{ fontSize: 10, color: "var(--muted)" }}>{opt.meta}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
