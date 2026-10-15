import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const API = process.env.RESQNET_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        // keep heavy libraries out of the entry chunk so the Command page loads fast
        manualChunks: { charts: ["recharts"], flow: ["@xyflow/react"], react: ["react", "react-dom", "react-router-dom"] },
      },
    },
  },
  server: {
    port: 5173,
    fs: { allow: [".."] }, // /research renders the repository's docs/ at build time
    proxy: {
      "/api": { target: API, changeOrigin: true },
      "/ws": { target: API.replace("http", "ws"), ws: true },
    },
  },
});
