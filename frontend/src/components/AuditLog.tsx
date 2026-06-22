/* Audit-log table — every correction, immutable (FR-016). */

import type { AuditEntry } from "../lib/api";

export function AuditLog({ rows }: { rows: AuditEntry[] }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", background: "var(--surface)" }}>
      {rows.map((a, i) => (
        <div
          key={i}
          style={{
            display: "grid",
            gridTemplateColumns: "80px 1fr 1.2fr 1fr",
            gap: 10,
            padding: "9px 16px",
            borderBottom: "1px solid var(--border-2)",
            fontSize: 12,
            alignItems: "center",
          }}
        >
          <span style={{ fontSize: 11, color: "var(--muted)" }}>{a.timestamp}</span>
          <span className="mono" style={{ fontWeight: 600 }}>
            {a.repo_id}
          </span>
          <span style={{ color: "var(--fg-2)" }}>{a.check_label}</span>
          <span className="mono" style={{ fontSize: 11, color: "var(--pass)", textAlign: "right" }}>
            {a.result}
          </span>
        </div>
      ))}
    </div>
  );
}
