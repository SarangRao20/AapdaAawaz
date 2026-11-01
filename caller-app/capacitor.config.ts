import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.aapda.awaaz",
  appName: "Aapda Awaaz",
  webDir: "dist",
  server: {
    // The app is served from http://localhost. "localhost" is still a secure
    // context, so getUserMedia works, and plain-HTTP calls to the VM API are
    // not blocked as mixed content (unlike an https://localhost origin).
    androidScheme: "http",
    cleartext: true,
  },
  android: {
    buildOptions: {
      keystorePath: undefined,
      keystoreAlias: undefined,
    },
  },
};

export default config;
