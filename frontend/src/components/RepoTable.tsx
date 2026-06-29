/* Fleet repo table (prototype): Repository / PRs / CI / License / Alerts / Release /
   Hygiene, with connection badge and the 🤖 bot-PR flag. Columns are sortable (click a
   header; click again to flip direction). Rows drill into the repo. */

import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { Overview } from "../lib/api";
import { ciViz, toneColor } from "../lib/status";
import { ConnectionBadge, HygieneBar } from "./widgets";

const GRID = "2fr 0.7fr 0.6fr 0.8fr 0.7fr 0.7fr 1fr";
type Row = NonNullable<Overview["repos"]>[number];
type Align = "left" | "right" | "center";
type SortKey = "id" | "open_prs" | "ci" | "license" | "alerts_total" | "release_pending_days" | "hygiene_pct";

// CI sorts by health (failing first when ascending), not the raw string.
const CI_RANK: Record<string, number> = { fail: 0, none: 1, pass: 2 };

const COLUMNS: { key: SortKey; label: string; align: Align; val: (r: Row) => number | string }[] = [
  { key: "id", label: "Repository", align: "left", val: (r) => r.id ?? "" },
  { key: "open_prs", label: "PRs", align: "right", val: (r) => r.open_prs ?? 0 },
  { key: "ci", label: "CI", align: "center", val: (r) => CI_RANK[r.ci ?? "none"] ?? 1 },
  { key: "license", label: "License", align: "center", val: (r) => r.license ?? "" },
  { key: "alerts_total", label: "Alerts", align: "right", val: (r) => r.alerts_total ?? 0 },
  // null release (no unreleased commits) sorts below any real day count.
  { key: "release_pending_days", label: "Release", align: "right", val: (r) => r.release_pending_days ?? -1 },
  { key: "hygiene_pct", label: "Hygiene", align: "right", val: (r) => r.hygiene_pct ?? 0 },
];

function releaseColor(days: number | null | undefined): string {
  if (days == null) return "var(--muted)";
  if (days >= 14) return "var(--fail)";
  if (days >= 7) return "var(--warn)";
  return "var(--muted)";
}

export function RepoTable({ repos }: { repos: Row[] }) {
  const navigate = useNavigate();
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return repos;
    const col = COLUMNS.find((c) => c.key === sort.key)!;
    return [...repos].sort((a, b) => {
      const av = col.val(a);
      const bv = col.val(b);
      if (av < bv) return -sort.dir;
      if (av > bv) return sort.dir;
      return 0;
    });
  }, [repos, sort]);

  function toggleSort(key: SortKey) {
    setSort((s) => (s && s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 }));
  }

  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden", background: "var(--surface)" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: GRID,
          gap: 8,
          padding: "9px 16px",
          fontSize: 10,
          color: "var(--muted)",
          textTransform: "uppercase",
          letterSpacing: "0.05em",
          fontWeight: 600,
          background: "var(--surface-2)",
          borderBottom: "1px solid var(--border)",
        }}
      >
        {COLUMNS.map((c) => {
          const active = sort?.key === c.key;
          return (
            <span
              key={c.key}
              onClick={() => toggleSort(c.key)}
              title={`Sort by ${c.label}`}
              style={{
                textAlign: c.align,
                cursor: "pointer",
                userSelect: "none",
                color: active ? "var(--fg)" : undefined,
                whiteSpace: "nowrap",
              }}
            >
              {c.label}
              <span style={{ opacity: active ? 1 : 0.25 }}>{active ? (sort!.dir === 1 ? " ▲" : " ▼") : " ↕"}</span>
            </span>
          );
        })}
      </div>
      {sorted.map((r) => {
        const ci = ciViz(r.ci ?? "none");
        const rel = r.release_pending_days;
        return (
          <div
            key={r.id}
            onClick={() => navigate(`/repos/${r.connection_id}/${r.id}`)}
            style={{
              display: "grid",
              gridTemplateColumns: GRID,
              gap: 8,
              padding: "11px 16px",
              alignItems: "center",
              borderBottom: "1px solid var(--border-2)",
              cursor: "pointer",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ lineHeight: 1.7 }}>
                <span style={{ fontWeight: 600, fontSize: 13, marginRight: 6 }}>{r.id}</span>
                <ConnectionBadge label={r.connection_badge ?? ""} />
              </div>
              <div
                style={{
                  fontSize: 11,
                  color: "var(--muted)",
                  marginTop: 2,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {r.description}
              </div>
            </div>
            <div className="mono" style={{ textAlign: "right", fontSize: 12, whiteSpace: "nowrap" }}>
              <span style={{ color: "var(--fg)" }}>{r.open_prs}</span>
              {(r.bot_prs ?? 0) > 0 && (
                <span style={{ color: "var(--warn)", fontSize: 10 }}> · {r.bot_prs} 🤖</span>
              )}
            </div>
            <div className="mono" style={{ textAlign: "center", fontSize: 13, color: ci.color }} title={ci.title}>
              {ci.glyph}
            </div>
            <div
              className="mono"
              style={{ textAlign: "center", fontSize: 11, color: r.license ? "var(--fg-2)" : "var(--muted)", whiteSpace: "nowrap" }}
              title={r.license ? `${r.license} license` : "No license detected"}
            >
              {r.license ?? "–"}
            </div>
            <div className="mono" style={{ textAlign: "right", fontSize: 12, color: toneColor((r.alerts_tone as never) ?? "neutral") }}>
              {(r.alerts_total ?? 0) > 0 ? r.alerts_total : "–"}
            </div>
            <div className="mono" style={{ textAlign: "right", fontSize: 12, color: releaseColor(rel) }}>
              {rel != null ? `${rel}d` : "–"}
            </div>
            <HygieneBar pct={r.hygiene_pct ?? 0} />
          </div>
        );
      })}
    </div>
  );
}
