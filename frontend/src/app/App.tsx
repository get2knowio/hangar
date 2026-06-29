/* App shell + routes for the five screens (T022).
   In oidc mode the shell is gated behind a session: the /auth/info probe decides whether to
   render the login screen. In forward-auth/disabled mode the probe always reports
   authenticated, so behavior is unchanged. */

import { Route, Routes } from "react-router-dom";
import { Catalog } from "../screens/Catalog";
import { Overview } from "../screens/Overview";
import { Providers } from "../screens/Providers";
import { RepoDetail } from "../screens/RepoDetail";
import { Scorecard } from "../screens/Scorecard";
import { Login } from "./Login";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { ToastHost } from "./state";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { useAuthInfo } from "../lib/api";

export function App() {
  const auth = useAuthInfo();

  // Gate only when the backend says OIDC is active and there's no session yet. While the
  // probe is in flight, render nothing (avoids a flash of the shell or the login screen).
  if (auth.isLoading) return null;
  if (auth.data?.mode === "oidc" && !auth.data.authenticated) {
    return <Login loginUrl={auth.data.login_url} />;
  }

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <Topbar />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <Sidebar />
        <div style={{ flex: 1, overflow: "auto", minWidth: 0 }}>
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/scorecard" element={<Scorecard />} />
              <Route path="/catalog" element={<Catalog />} />
              <Route path="/providers" element={<Providers />} />
              <Route path="/repos/:connectionId/:id" element={<RepoDetail />} />
            </Routes>
          </ErrorBoundary>
        </div>
      </div>
      <ToastHost />
    </div>
  );
}
