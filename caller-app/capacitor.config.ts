import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.aapda.awaaz",
  appName: "Aapda Awaaz",
  webDir: "dist",
  server: {
    // For local dev with live-reload; remove before release APK
    // url: "http://192.168.x.x:5173",
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
