# Aapda Awaaz — Caller App

Voice emergency-reporting app (React + Vite + Capacitor Android).

## Build

```bash
npm install
ANDROID_HOME=$ANDROID_HOME JAVA_HOME=/usr/lib/jvm/java-21-openjdk ./build-apk.sh
```

The APK lands at `../AapdaAwaaz-caller.apk`.

## API URL

`src/api.ts` reads `VITE_API_URL`, which Vite inlines at **build time**. It is not
committed (`.env` is gitignored), so create it before building:

```bash
echo "VITE_API_URL=https://your-api.example.com" > .env
```

Without it the app falls back to `http://localhost:8000`, which on a phone means
the phone itself.

`capacitor.config.ts` uses `androidScheme: "http"` so the WebView serves from
`http://localhost` — still a secure context, so `getUserMedia` (microphone) works,
and plain-HTTP API calls are not blocked as mixed content.

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
