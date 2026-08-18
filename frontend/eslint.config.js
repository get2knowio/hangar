// Flat ESLint config (ESLint 10). Replaces the legacy .eslintrc.cjs — flat config is
// the only supported format from ESLint 9 on. Same rule intent as before: the recommended
// JS + TypeScript sets, React Hooks rules, `no-explicit-any` as a warning, and the
// react-refresh export rule left off (context hooks/helpers are co-located with providers).
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "src/lib/api-types.ts", "node_modules", "playwright-report"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs.flat["recommended-latest"],
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser },
    },
    plugins: { "react-refresh": reactRefresh },
    rules: {
      "react-refresh/only-export-components": "off",
      "@typescript-eslint/no-explicit-any": "warn",
      // New in eslint-plugin-react-hooks 7; flags a couple of intentional
      // seed-local-state-from-fetched-data / reactive-form-field patterns in
      // ConnectionModals. Off here to keep this tooling migration behavior-preserving;
      // refactoring those effects is tracked as separate follow-up work.
      "react-hooks/set-state-in-effect": "off",
    },
  },
);
