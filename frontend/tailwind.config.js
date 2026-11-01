/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--c-bg) / <alpha-value>)",
        surface: {
          1: "rgb(var(--c-s1) / <alpha-value>)",
          2: "rgb(var(--c-s2) / <alpha-value>)",
          3: "rgb(var(--c-s3) / <alpha-value>)",
        },
        line: {
          DEFAULT: "rgb(var(--c-line) / <alpha-value>)",
          strong: "rgb(var(--c-lines) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--c-ink) / <alpha-value>)",
          2: "rgb(var(--c-ink2) / <alpha-value>)",
          3: "rgb(var(--c-ink3) / <alpha-value>)",
        },
        accent: { DEFAULT: "#f97316", dim: "#c2410c", glow: "#fb923c" },
        status: { good: "#22c55e", warning: "#f59e0b", serious: "#f97316", critical: "#ef4444" },
      },
      fontFamily: {
        sans: ['"Inter Variable"', "Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "JetBrains Mono", "Consolas", "monospace"],
      },
      fontSize: { "2xs": ["0.6875rem", "1rem"] },
      boxShadow: {
        glass: "0 1px 3px rgba(0,0,0,0.4)",
        glow: "0 0 0 1px rgba(249,115,22,0.3), 0 0 20px -4px rgba(249,115,22,0.2)",
        crit: "0 0 0 1px rgba(239,68,68,0.4), 0 0 20px -6px rgba(239,68,68,0.3)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(0.6)", opacity: "0.7" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        shrink: { "0%": { transform: "scaleX(1)" }, "100%": { transform: "scaleX(0)" } },
        "aurora": {
          "0%,100%": { transform: "translate3d(0,0,0) scale(1)" },
          "50%": { transform: "translate3d(4%,-3%,0) scale(1.12)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 2.2s cubic-bezier(0.2,0.6,0.3,1) infinite",
        shimmer: "shimmer 1.8s infinite",
        shrink: "shrink 9s linear forwards",
        aurora: "aurora 18s ease-in-out infinite",
        "fade-up": "fade-up 0.4s ease-out both",
      },
    },
  },
  plugins: [],
};
