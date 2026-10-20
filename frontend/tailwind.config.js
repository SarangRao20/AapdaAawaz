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
        accent: { DEFAULT: "#4d9dff", dim: "#2563b8", glow: "#7cb8ff" },
        status: { good: "#2fd06b", warning: "#fab219", serious: "#ff8a5c", critical: "#ff4d4d" },
      },
      fontFamily: {
        sans: ['"Inter Variable"', "Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono Variable"', "JetBrains Mono", "Consolas", "monospace"],
      },
      fontSize: { "2xs": ["0.6875rem", "1rem"] },
      boxShadow: {
        glass: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 12px 40px -12px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(77,157,255,0.35), 0 0 32px -4px rgba(77,157,255,0.35)",
        crit: "0 0 0 1px rgba(255,77,77,0.4), 0 0 36px -6px rgba(255,77,77,0.45)",
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
