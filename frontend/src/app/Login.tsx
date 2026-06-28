/* OIDC sign-in screen. Shown by the AuthGate only in oidc mode when there is no session.
   "Sign in" is a full navigation (not a fetch) to /auth/login, which 302s to the IdP. */

export function Login({ loginUrl }: { loginUrl: string }) {
  return (
    <div
      style={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 22,
        background: "var(--bg)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 8,
            background: "var(--fg)",
            color: "var(--bg)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontWeight: 800,
            fontSize: 18,
          }}
        >
          n
        </div>
        <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>Hangar</span>
      </div>
      <div style={{ fontSize: 13, color: "var(--muted)" }}>Sign in to continue</div>
      <a
        href={loginUrl}
        style={{
          fontSize: 14,
          fontWeight: 600,
          padding: "10px 22px",
          borderRadius: 8,
          border: "1px solid var(--fg)",
          background: "var(--fg)",
          color: "var(--bg)",
          textDecoration: "none",
        }}
      >
        Sign in with SSO
      </a>
    </div>
  );
}
