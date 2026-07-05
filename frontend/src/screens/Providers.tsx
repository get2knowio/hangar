/* Providers & access (/providers) — access banner, connection cards, audit log
   (FR-021–FR-032). Access state is wired from /providers + /me (T074). */

import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { AuditLog } from "../components/AuditLog";
import { AddConnectionModal, RemoveConnectionModal, RepoPickerModal } from "../components/ConnectionModals";
import { ErrorState } from "../components/ErrorState";
import { useToast } from "../app/state";
import { useAudit, useProviders, useSyncConnection } from "../lib/api";

export function Providers() {
  const { data, isLoading, isError, error, refetch } = useProviders();
  const audit = useAudit();
  const syncConn = useSyncConnection();
  const { show } = useToast();
  const [addOpen, setAddOpen] = useState(false);
  const [picker, setPicker] = useState<{ id: string; label: string } | null>(null);
  const [removing, setRemoving] = useState<{ id: string; label: string } | null>(null);
  const [params, setParams] = useSearchParams();

  // The "Connect with GitHub" flow returns the browser here with ?connected=<id> on success
  // or ?connect_error=<reason> on failure. Surface it, refresh the list, and clear the query.
  useEffect(() => {
    const connected = params.get("connected");
    const connectError = params.get("connect_error");
    if (connected) {
      show(`Connected · ${connected}`);
      refetch();
      setParams({}, { replace: true });
    } else if (connectError) {
      show(`Couldn’t connect to GitHub (${connectError.replace(/_/g, " ")})`, "error");
      setParams({}, { replace: true });
    }
  }, [params, show, refetch, setParams]);

  if (isError) {
    return <ErrorState title="Couldn't load providers" error={error} onRetry={refetch} />;
  }
  if (isLoading || !data) {
    return <div style={{ padding: "24px 28px", color: "var(--muted)" }}>Loading providers…</div>;
  }

  const access = data.access;
  const enforced = access?.mode === "forward-auth";
  const allowed = access?.allowed_user ? ` · allowed=${access.allowed_user}` : "";

  return (
    <div style={{ padding: "24px 28px", maxWidth: 920 }}>
      <h1 style={{ margin: "0 0 4px", fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>Providers & access</h1>
      <p style={{ margin: "0 0 20px", fontSize: 13, color: "var(--muted)" }}>
        The way in is a homelab construct. Talking to a platform is a provider construct. Decoupled on
        purpose.
      </p>

      <div
        style={{
          border: "1px solid var(--border)",
          borderRadius: 8,
          background: "var(--surface-2)",
          padding: "15px 18px",
          marginBottom: 24,
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: enforced ? "var(--pass)" : "var(--warn)", flex: "none" }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {enforced ? "Access enforced at the homelab edge — forward-auth" : "Access control disabled (network-trust)"}
          </div>
          <div className="mono" style={{ fontSize: 11, color: "var(--muted)", marginTop: 3 }}>
            HANGAR_FORWARD_AUTH={enforced ? "enabled" : "disabled"} · header {access?.user_header}
            {allowed} · fail-closed when unset
          </div>
        </div>
        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--pass)", background: "var(--pass-bg)", borderRadius: 6, padding: "5px 11px" }}>
          Behind Traefik
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)" }}>
          Provider connections
        </div>
        <button
          onClick={() => setAddOpen(true)}
          style={{ fontSize: 12, fontWeight: 600, color: "var(--fg)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 12px", cursor: "pointer", background: "transparent", fontFamily: "inherit" }}
        >
          + Add connection
        </button>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 28 }}>
        {(data.connections ?? []).map((cn) => (
          <div key={cn.id} style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--surface)", padding: "16px 18px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--pass)", flex: "none" }} />
              <span className="mono" style={{ fontSize: 14, fontWeight: 700 }}>
                {cn.label}
              </span>
              <span style={{ fontSize: 10, fontWeight: 600, color: "var(--fg-2)", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 8px" }}>
                {cn.type}
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: cn.writes ? "var(--pass)" : "var(--warn)",
                  background: cn.writes ? "var(--pass-bg)" : "var(--warn-bg)",
                  borderRadius: 5,
                  padding: "3px 9px",
                }}
              >
                {cn.write_label}
              </span>
              <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)" }}>synced {cn.synced}</span>
              {(() => {
                const pending = syncConn.isPending && syncConn.variables === cn.id;
                return (
                  <button
                    onClick={() =>
                      syncConn.mutate(cn.id ?? "", {
                        onSuccess: () => show(`Refreshed · ${cn.label}`),
                        onError: () => show(`Refresh failed · ${cn.label}`, "error"),
                      })
                    }
                    disabled={syncConn.isPending}
                    title="Re-interrogate this connection now"
                    style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, fontWeight: 600, color: "var(--fg)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 10px", cursor: syncConn.isPending ? "default" : "pointer", background: "transparent", fontFamily: "inherit", opacity: syncConn.isPending && !pending ? 0.5 : 1 }}
                  >
                    <span style={{ display: "inline-block", animation: pending ? "hgspin .8s linear infinite" : undefined }}>↻</span>
                    {pending ? "Refreshing…" : "Refresh"}
                  </button>
                );
              })()}
              <button
                onClick={() => setPicker({ id: cn.id ?? "", label: cn.label ?? "" })}
                style={{ fontSize: 11, fontWeight: 600, color: "var(--fg)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 10px", cursor: "pointer", background: "transparent", fontFamily: "inherit" }}
              >
                Manage repos
              </button>
              <button
                onClick={() => setRemoving({ id: cn.id ?? "", label: cn.label ?? "" })}
                title="Remove this connection"
                style={{ fontSize: 11, fontWeight: 600, color: "var(--warn)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 10px", cursor: "pointer", background: "transparent", fontFamily: "inherit" }}
              >
                Remove
              </button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 14, marginTop: 14 }}>
              <Field label="Scope" value={cn.scope ?? ""} />
              <Field label="Auth" value={cn.auth_mode ?? ""} />
              <Field
                label="Repos"
                value={`${cn.repos} · ${cn.repo_allowlist ? "selected" : "all"}`}
                mono
              />
              <Field label="Remediation" value={cn.remediation ?? ""} />
            </div>
          </div>
        ))}
      </div>

      <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--muted)", marginBottom: 10 }}>
        Audit log — every correction
      </div>
      <AuditLog rows={(audit.data ?? []).slice(0, 6)} />

      {addOpen && (
        <AddConnectionModal
          onClose={() => setAddOpen(false)}
          onAdded={(card) => {
            // Jump straight into picking repos for the freshly-added connection.
            setAddOpen(false);
            setPicker({ id: card.id ?? "", label: card.label ?? "" });
          }}
        />
      )}
      {picker && (
        <RepoPickerModal
          connectionId={picker.id}
          connectionLabel={picker.label}
          onClose={() => setPicker(null)}
        />
      )}
      {removing && (
        <RemoveConnectionModal
          connectionId={removing.id}
          connectionLabel={removing.label}
          onClose={() => setRemoving(null)}
        />
      )}
    </div>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.04em" }}>{label}</div>
      <div className={mono ? "mono" : undefined} style={{ fontSize: 13, marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}
