import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.hitorro.solarsage",
  appName: "SolarSage",
  webDir: "dist",
  bundledWebRuntime: false,
  server: {
    // In production builds the bundled `dist/` is served from
    // `capacitor://localhost` (iOS) or `http://localhost` (Android).
    // During development you can flip this to point at the Vite dev server
    // on your Mac's LAN IP, e.g. http://192.168.1.123:5173.
    androidScheme: "http",
    iosScheme: "capacitor",
  },
  ios: {
    contentInset: "automatic",
  },
};

export default config;
