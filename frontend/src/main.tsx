import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./app/App";
import { ConnectionProvider, ThemeProvider, ToastProvider } from "./app/state";
import "./index.css";

const queryClient = new QueryClient({
  // Dashboards are snapshot/poll-driven (server polls every ~5 min), so cached reads
  // need not re-run the heavy aggregations on every navigation. Mutations invalidate
  // the relevant keys explicitly for immediate freshness.
  defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ConnectionProvider>
          <ToastProvider>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </ToastProvider>
        </ConnectionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
