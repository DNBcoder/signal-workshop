import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  define: {
    "process.env.BACKEND_URL": JSON.stringify(process.env.BACKEND_URL || ""),
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": process.env.BACKEND_URL || "http://127.0.0.1:8000",
    },
  },
});

