import type { Config } from "tailwindcss";

/* Tailwind maps the prototype's CSS-variable tokens so utility classes and inline
   var(--token) styles share one source of truth (contracts/ui-spec.md). */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        border: "var(--border)",
        "border-2": "var(--border-2)",
        fg: "var(--fg)",
        "fg-2": "var(--fg-2)",
        muted: "var(--muted)",
        hover: "var(--hover)",
        pass: "var(--pass)",
        warn: "var(--warn)",
        fail: "var(--fail)",
        unknown: "var(--unknown)",
      },
      fontFamily: {
        sans: ["Public Sans", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
