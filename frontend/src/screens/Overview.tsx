/* Fleet overview (/) — six stat tiles, repo table, attention feed (FR-001–FR-004). */

import { useNavigate } from "react-router-dom";
import { AttentionFeed } from "../components/AttentionFeed";
import { ErrorState } from "../components/ErrorState";
import { RepoTable } from "../components/RepoTable";
import { StatTile } from "../components/widgets";
import { useConnection } from "../app/state";
import { useOverview, useProviders } from "../lib/api";
import type { Tone } from "../lib/status";

export function Overview() {
  const { active } = useConnection();
  const { data, isLoading, isError, error, refetch } = useOverview(active);
  const providers = useProviders();
  const navigate = useNavigate();

  const scopeLabel =
    active === "all"
      ? "all connections"
      : (providers.data?.connections?.find((c) => c.id === active)?.label ?? active);

  if (isError) {
    return <ErrorState title="Couldn't load the fleet" error={error} onRetry={refetch} />;
  }
  if (isLoading || !data) {
    return <div style={{ padding: "24px 28px", color: "var(--muted)" }}>Loading fleet…</div>;
  }

  const repos = data.repos ?? [];
  if (repos.length === 0) {
    return (
      <div style={{ padding: "48px 28px", maxWidth: 560 }}>
        <h1 style={{ margin: "0 0 6px", fontSize: 22, fontWeight: 700 }}>No repositories yet</h1>
        <p style={{ fontSize: 13, color: "var(--muted)", marginBottom: 18 }}>
          The fleet is the union of repositories across your provider connections. Add a connection
          to start watching repos — no per-repo setup required.
        </p>
        <div
          onClick={() => navigate("/providers")}
          style={{
            display: "inline-block",
            fontSize: 13,
            fontWeight: 600,
            color: "var(--bg)",
            background: "var(--fg)",
            borderRadius: 6,
            padding: "8px 14px",
            cursor: "pointer",
          }}
        >
          Add a connection →
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: "24px 28px", maxWidth: 1180 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>Fleet overview</h1>
        <span style={{ fontSize: 12, color: "var(--muted)" }}>
          {data.summary?.repo_count} repos · {data.summary?.compliance_pct}% compliant
        </span>
      </div>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: "var(--muted)" }}>
        What needs attention right now, across {scopeLabel}.
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(6,1fr)",
          gap: 1,
          background: "var(--border)",
          border: "1px solid var(--border)",
          borderRadius: 8,
          overflow: "hidden",
          marginBottom: 20,
        }}
      >
        {(data.stats ?? []).map((s) => (
          <StatTile
            key={s.label}
            label={s.label ?? ""}
            value={s.value ?? ""}
            sub={s.sub ?? ""}
            tone={(s.tone as Tone) ?? "neutral"}
            subTone={(s.sub_tone as Tone) ?? "neutral"}
          />
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 360px", gap: 20, alignItems: "start" }}>
        <RepoTable repos={repos} />
        <AttentionFeed feed={data.feed ?? []} />
      </div>
    </div>
  );
}
