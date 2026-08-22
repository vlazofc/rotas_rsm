import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom", "react-router-dom"],
          map: ["leaflet"],
        },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    // Em dev, encaminha /api para a API local
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
