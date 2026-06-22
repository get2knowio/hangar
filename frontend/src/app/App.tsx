/* App shell + routes for the five screens (T022). */

import { Route, Routes } from "react-router-dom";
import { Catalog } from "../screens/Catalog";
import { Overview } from "../screens/Overview";
import { Providers } from "../screens/Providers";
import { RepoDetail } from "../screens/RepoDetail";
import { Scorecard } from "../screens/Scorecard";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { ToastHost } from "./state";

export function App() {
  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <Topbar />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <Sidebar />
        <div style={{ flex: 1, overflow: "auto", minWidth: 0 }}>
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/scorecard" element={<Scorecard />} />
            <Route path="/catalog" element={<Catalog />} />
            <Route path="/providers" element={<Providers />} />
            <Route path="/repos/:id" element={<RepoDetail />} />
          </Routes>
        </div>
      </div>
      <ToastHost />
    </div>
  );
}
