import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Newer Vite (5.x+) blocks unknown Host headers as an SSRF guard.
    // Apache reverse-proxies SolarSage on several names, so allowlist
    // the ones we serve behind. Add more here if you invent new
    // ServerAlias entries in the apache vhost.
    allowedHosts: [
      "pi-sf.hitorro.com",
      "pi-sf",
      "pi5",
      "pi5.hitorro.com",
      "pi-ha",
      "pi-ha.hitorro.com",
      "localhost",
      "127.0.0.1",
    ],
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
