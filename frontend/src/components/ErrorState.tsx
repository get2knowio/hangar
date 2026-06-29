/* Inline error panel for a failed data load. A screen must never sit on a forever
   "Loading…" or a blank page when a request fails (401 after a session expiry, a 502 from
   the proxy, a dropped connection) — it states what happened and offers the way forward,
   in the interface's voice. */

type HttpError = { status?: number };

function explain(error: unknown): string {
  const status = (error as HttpError)?.status;
  if (status === 401 || status === 403) return "Your session has ended. Reload to sign back in.";
  if (status === 404) return "That resource is no longer available.";
  if (status && status >= 500) return "The server returned an error. It's usually temporary — try again.";
  return "Couldn't reach the server. Check your connection, then try again.";
}

export function ErrorState({
  title,
  error,
  onRetry,
}: {
  title: string;
  error?: unknown;
  onRetry?: () => void;
}) {
  return (
    <div style={{ padding: "48px 28px", maxWidth: 560 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 6 }}>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--fail)", flex: "none" }} />
        <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>{title}</h1>
      </div>
      <p style={{ fontSize: 13, color: "var(--muted)", margin: "0 0 18px" }}>{explain(error)}</p>
      {onRetry && (
        <button
          onClick={() => onRetry()}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            fontSize: 13,
            fontWeight: 600,
            color: "var(--bg)",
            background: "var(--fg)",
            border: "none",
            borderRadius: 6,
            padding: "8px 14px",
            cursor: "pointer",
            fontFamily: "inherit",
          }}
        >
          ↻ Try again
        </button>
      )}
    </div>
  );
}
