import { readFileSync } from "node:fs";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Bake the package version into the bundle so the UI can show exactly which build is running.
// Read here (not imported from src) to keep package.json out of the TS rootDir/include.
const pkgVersion = JSON.parse(
  readFileSync(new URL("./package.json", import.meta.url), "utf-8"),
).version as string;

// SPA dev server proxies /api and /auth → the FastAPI backend on :8000 (quickstart.md).
export default defineConfig({
  plugins: [react()],
  // Compile-time constant; declared in src/vite-env.d.ts. Applies to the build and to vitest.
  define: {
    __APP_VERSION__: JSON.stringify(pkgVersion),
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      // OIDC login/callback/logout + the pre-login probe live under /auth (not /api/v1).
      "/auth": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/unit/**/*.test.{ts,tsx}"],
  },
});
