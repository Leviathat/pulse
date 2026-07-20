import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api to the local API so the browser talks to one origin
// (mirrors the nginx proxy used in the container).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
