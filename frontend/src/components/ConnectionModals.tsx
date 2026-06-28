/* Add-connection wizard + per-connection repo picker. Both post through the typed client
   (useAddConnection / useSetConnectionRepos); the repo allowlist is the FR-021–FR-026
   connection-scoping surface — a connection watches all repos by default, or exactly the
   selected subset. Styling mirrors the ScorecardMatrix modal (fixed backdrop + panel). */

import { useEffect, useMemo, useState, type ReactNode } from "react";

import { useToast } from "../app/state";
import {
  useAddConnection,
  useConnectionRepos,
  useSetConnectionRepos,
  type ConnectionCard,
  type NewConnectionBody,
} from "../lib/api";

function Backdrop({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,.35)", zIndex: 90,
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10,
          padding: "20px 22px", width: 460, maxHeight: "85vh", overflowY: "auto",
          boxShadow: "0 12px 40px rgba(0,0,0,.3)",
        }}
      >
        {children}
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em",
  color: "var(--muted)", display: "block", marginBottom: 4,
};
const inputStyle: React.CSSProperties = {
  width: "100%", fontSize: 13, padding: "7px 10px", borderRadius: 6,
  border: "1px solid var(--border)", background: "var(--surface-2)", color: "var(--fg)",
  boxSizing: "border-box", fontFamily: "inherit",
};
const primaryBtn: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, padding: "8px 15px", borderRadius: 6,
  border: "1px solid var(--fg)", background: "var(--fg)", color: "var(--bg)", cursor: "pointer",
};
const ghostBtn: React.CSSProperties = {
  fontSize: 12, fontWeight: 600, padding: "8px 13px", borderRadius: 6,
  border: "1px solid var(--border)", background: "transparent", color: "var(--fg-2)", cursor: "pointer",
};

// A small padlock shown to the right of private repos in the picker.
function Lock() {
  return (
    <svg
      width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
      style={{ marginLeft: "auto", color: "var(--muted)", flex: "none" }}
      role="img" aria-label="Private repository"
    >
      <title>Private</title>
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </svg>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 13 }}>
      <label style={labelStyle}>{label}</label>
      {children}
    </div>
  );
}

// ---- Add connection ----------------------------------------------------------------
export function AddConnectionModal({
  onClose,
  onAdded,
}: {
  onClose: () => void;
  onAdded: (card: ConnectionCard) => void;
}) {
  const add = useAddConnection();
  const { show } = useToast();
  const [providerType, setProviderType] = useState<"github" | "gitea">("github");
  const [label, setLabel] = useState("");
  const [owner, setOwner] = useState("");
  const [scope, setScope] = useState("");
  const [credential, setCredential] = useState("");
  const [appId, setAppId] = useState("");
  const [installationId, setInstallationId] = useState("");
  const [writable, setWritable] = useState(false);

  // Owner defaults to the label suffix (gh:my-org → my-org), mirroring the backend.
  const derivedOwner = owner.trim() || (label.includes(":") ? label.split(":").pop()! : label).trim();
  const writableNeedsCred = writable && !credential.trim();
  const canSubmit = label.trim().length > 0 && !writableNeedsCred && !add.isPending;

  function submit() {
    if (!canSubmit) return;
    const body: NewConnectionBody = {
      provider_type: providerType,
      label: label.trim(),
      scope: scope.trim() || `${providerType === "gitea" ? "user" : "org"} · ${derivedOwner}`,
      owner: derivedOwner || undefined,
      credential: credential.trim() || undefined,
      app_id: appId.trim() || undefined,
      installation_id: installationId.trim() ? Number(installationId.trim()) : undefined,
      writable,
    };
    add.mutate(body, {
      onSuccess: ({ data }) => {
        show(`Connected ${data.label}`);
        onAdded(data);
      },
      onError: (e: unknown) => show(e instanceof Error ? e.message : "Could not add connection"),
    });
  }

  return (
    <Backdrop onClose={onClose}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>Add connection</div>
      <p style={{ fontSize: 12, color: "var(--muted)", margin: "0 0 16px" }}>
        A Personal Access Token is the simplest path; leave App fields blank. For a GitHub App,
        paste the private-key PEM as the credential and fill in the App + installation ids.
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Provider">
          <select style={inputStyle} value={providerType} onChange={(e) => setProviderType(e.target.value as "github" | "gitea")}>
            <option value="github">GitHub</option>
            <option value="gitea">Gitea</option>
          </select>
        </Field>
        <Field label="Label">
          <input style={inputStyle} placeholder="gh:my-org" value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="Owner (org / user)">
          <input style={inputStyle} placeholder={derivedOwner || "my-org"} value={owner} onChange={(e) => setOwner(e.target.value)} />
        </Field>
        <Field label="Scope (display)">
          <input style={inputStyle} placeholder="org · my-org" value={scope} onChange={(e) => setScope(e.target.value)} />
        </Field>
      </div>

      <Field label="Credential — PAT, or App private-key PEM">
        <textarea
          style={{ ...inputStyle, minHeight: 64, resize: "vertical" }}
          placeholder="ghp_… or -----BEGIN PRIVATE KEY-----"
          value={credential}
          onChange={(e) => setCredential(e.target.value)}
        />
      </Field>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        <Field label="App id (App only)">
          <input style={inputStyle} placeholder="optional" value={appId} onChange={(e) => setAppId(e.target.value)} />
        </Field>
        <Field label="Installation id (App only)">
          <input style={inputStyle} placeholder="optional" inputMode="numeric" value={installationId} onChange={(e) => setInstallationId(e.target.value)} />
        </Field>
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13, margin: "4px 0 6px", cursor: "pointer" }}>
        <input type="checkbox" checked={writable} onChange={(e) => setWritable(e.target.checked)} />
        Writable — allow Hangar to open fix PRs (least-privilege: off by default)
      </label>
      {writableNeedsCred && (
        <div style={{ fontSize: 11, color: "var(--warn)", marginBottom: 8 }}>
          A writable connection requires a credential.
        </div>
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
        <button style={ghostBtn} onClick={onClose} disabled={add.isPending}>Cancel</button>
        <button style={{ ...primaryBtn, opacity: canSubmit ? 1 : 0.5, cursor: canSubmit ? "pointer" : "default" }} onClick={submit} disabled={!canSubmit}>
          {add.isPending ? "Connecting…" : "Add connection"}
        </button>
      </div>
    </Backdrop>
  );
}

// ---- Repo picker -------------------------------------------------------------------
export function RepoPickerModal({
  connectionId,
  connectionLabel,
  onClose,
}: {
  connectionId: string;
  connectionLabel: string;
  onClose: () => void;
}) {
  const { data, isLoading, isError, error } = useConnectionRepos(connectionId, true);
  const save = useSetConnectionRepos(connectionId);
  const { show } = useToast();

  const [watchAll, setWatchAll] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");

  // Seed local state once the live repo list arrives.
  useEffect(() => {
    if (!data) return;
    setWatchAll(data.watching_all ?? true);
    setSelected(new Set(data.selected ?? (data.available ?? []).map((r) => r.name)));
  }, [data]);

  const available = useMemo(() => data?.available ?? [], [data]);
  const visible = useMemo(
    () => available.filter((r) => r.name.toLowerCase().includes(filter.toLowerCase())),
    [available, filter],
  );

  function toggle(repo: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(repo)) next.delete(repo);
      else next.add(repo);
      return next;
    });
  }

  function commit() {
    const repos = watchAll ? null : [...selected];
    save.mutate(repos, {
      onSuccess: () =>
        show(repos === null ? "Watching all repos" : `Watching ${repos.length} repo${repos.length === 1 ? "" : "s"}`),
      onError: (e: unknown) => show(e instanceof Error ? e.message : "Could not update selection"),
    });
    onClose();
  }

  const selectedCount = watchAll ? available.length : selected.size;

  return (
    <Backdrop onClose={onClose}>
      <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>
        Repos — <span className="mono">{connectionLabel}</span>
      </div>
      <p style={{ fontSize: 12, color: "var(--muted)", margin: "0 0 14px" }}>
        Choose which repos this connection watches. De-selected repos are never polled and
        leave the dashboard; this bounds GitHub API spend.
      </p>

      <label style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 13, marginBottom: 12, cursor: "pointer" }}>
        <input type="checkbox" checked={watchAll} onChange={(e) => setWatchAll(e.target.checked)} />
        Watch all repos (no filter)
      </label>

      {isLoading && <div style={{ fontSize: 13, color: "var(--muted)", padding: "18px 0" }}>Loading repos…</div>}
      {isError && (
        <div style={{ fontSize: 13, color: "var(--warn)", padding: "12px 0" }}>
          {error instanceof Error ? error.message : "Could not list repos."}
        </div>
      )}

      {!isLoading && !isError && (
        <>
          <input
            style={{ ...inputStyle, marginBottom: 8, opacity: watchAll ? 0.5 : 1 }}
            placeholder={`Filter ${available.length} repos…`}
            value={filter}
            disabled={watchAll}
            onChange={(e) => setFilter(e.target.value)}
          />
          <div style={{ border: "1px solid var(--border)", borderRadius: 8, maxHeight: 280, overflowY: "auto", opacity: watchAll ? 0.5 : 1 }}>
            {visible.length === 0 && (
              <div style={{ fontSize: 12, color: "var(--muted)", padding: "14px 12px" }}>
                {available.length === 0 ? "No repos visible to this credential." : "No matches."}
              </div>
            )}
            {visible.map((repo) => (
              <label
                key={repo.name}
                style={{
                  display: "flex", alignItems: "center", gap: 9, fontSize: 13, padding: "7px 12px",
                  borderBottom: "1px solid var(--border)", cursor: watchAll ? "default" : "pointer",
                }}
              >
                <input
                  type="checkbox"
                  disabled={watchAll}
                  checked={watchAll || selected.has(repo.name)}
                  onChange={() => toggle(repo.name)}
                />
                <span className="mono">{repo.name}</span>
                {repo.private && <Lock />}
              </label>
            ))}
          </div>
        </>
      )}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 16 }}>
        <span style={{ fontSize: 11, color: "var(--muted)" }}>
          {watchAll ? "Watching all" : `${selectedCount} selected`}
        </span>
        <div style={{ display: "flex", gap: 8 }}>
          <button style={ghostBtn} onClick={onClose} disabled={save.isPending}>Cancel</button>
          <button
            style={{ ...primaryBtn, opacity: save.isPending ? 0.5 : 1 }}
            onClick={commit}
            disabled={save.isPending || isLoading || isError}
          >
            {save.isPending ? "Saving…" : "Save selection"}
          </button>
        </div>
      </div>
    </Backdrop>
  );
}
