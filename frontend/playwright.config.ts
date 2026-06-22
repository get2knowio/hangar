import { defineConfig } from "@playwright/test";

/* Playwright drives the prototype flows against the dev server (quickstart scenarios
   B–F, H). The backend must be running on :8000 (seeded) and the SPA on :5173. */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  use: { baseURL: "http://127.0.0.1:5173", trace: "on-first-retry" },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
