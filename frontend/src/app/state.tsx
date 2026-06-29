/* Cross-screen client state: theme (persisted token swap), the active connection
   filter, and the toast host — all mirroring the prototype's behavior. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

// ---- Theme ----
type Theme = "light" | "dark";
interface ThemeCtx {
  theme: Theme;
  toggle: () => void;
}
const ThemeContext = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("hangar-theme") as Theme) || "light",
  );
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("hangar-theme", theme);
  }, [theme]);
  const toggle = useCallback(() => setTheme((t) => (t === "light" ? "dark" : "light")), []);
  const value = useMemo(() => ({ theme, toggle }), [theme, toggle]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
export const useTheme = () => {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme outside provider");
  return ctx;
};

// ---- Connection filter ----
interface ConnCtx {
  active: string; // "all" | connection id
  setActive: (id: string) => void;
}
const ConnectionContext = createContext<ConnCtx | null>(null);
export function ConnectionProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState("all");
  const value = useMemo(() => ({ active, setActive }), [active]);
  return <ConnectionContext.Provider value={value}>{children}</ConnectionContext.Provider>;
}
export const useConnection = () => {
  const ctx = useContext(ConnectionContext);
  if (!ctx) throw new Error("useConnection outside provider");
  return ctx;
};

// ---- Toast ----
// A toast carries a tone so a failure doesn't render with the same green dot as a success
// (an error that looks like a success is worse than no toast). Errors linger longer because
// they need to be read, and announce assertively for screen readers.
export type ToastTone = "success" | "error";
interface ToastState {
  message: string;
  tone: ToastTone;
}
interface ToastCtx {
  toast: ToastState | null;
  show: (message: string, tone?: ToastTone) => void;
}
const ToastContext = createContext<ToastCtx | null>(null);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const show = useCallback((message: string, tone: ToastTone = "success") => {
    setToast({ message, tone });
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), tone === "error" ? 4500 : 2600);
  }, []);
  const value = useMemo(() => ({ toast, show }), [toast, show]);
  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}
export const useToast = () => {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast outside provider");
  return ctx;
};

export function ToastHost() {
  const { toast } = useToast();
  if (!toast) return null;
  const isError = toast.tone === "error";
  return (
    <div
      role="status"
      aria-live={isError ? "assertive" : "polite"}
      style={{
        position: "fixed",
        bottom: 22,
        left: "50%",
        transform: "translateX(-50%)",
        background: "var(--fg)",
        color: "var(--bg)",
        fontSize: 13,
        fontWeight: 600,
        padding: "10px 18px",
        borderRadius: 8,
        boxShadow: "0 8px 28px rgba(0,0,0,.22)",
        // A hairline accent in the tone's color reinforces the dot for anyone who reads the
        // shape before the color (kept subtle so success stays quiet).
        borderLeft: `3px solid ${isError ? "var(--fail)" : "var(--pass)"}`,
        zIndex: 100,
        animation: "hgfade .15s ease",
        display: "flex",
        alignItems: "center",
        gap: 9,
      }}
    >
      <span style={{ width: 7, height: 7, borderRadius: "50%", background: isError ? "var(--fail)" : "var(--pass)" }} />
      {toast.message}
    </div>
  );
}
