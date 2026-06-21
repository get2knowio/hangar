/* eslint config (flat-config-free for tooling stability). */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: "latest", sourceType: "module" },
  plugins: ["@typescript-eslint", "react-refresh"],
  ignorePatterns: ["dist", "src/lib/api-types.ts", "node_modules", "playwright-report"],
  rules: {
    // We intentionally co-locate context hooks/helpers with their providers.
    "react-refresh/only-export-components": "off",
    "@typescript-eslint/no-explicit-any": "warn",
  },
};
