/* Last-resort guard: a render error in one screen must not white-screen the whole app.
   Catches the throw, logs it, and offers a reload instead of an unrecoverable blank page. */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Hangar UI crashed:", error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ padding: "64px 28px", maxWidth: 560 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9, marginBottom: 6 }}>
          <span style={{ width: 9, height: 9, borderRadius: "50%", background: "var(--fail)", flex: "none" }} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>This screen hit an error</h1>
        </div>
        <p style={{ fontSize: 13, color: "var(--muted)", margin: "0 0 18px" }}>
          Something in the page failed to render. Reloading usually clears it.
        </p>
        <button
          onClick={() => window.location.reload()}
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
          ↻ Reload Hangar
        </button>
      </div>
    );
  }
}
