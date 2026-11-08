import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the UI on :5173 and forwards /api to a running
// `python -m cpldglue gui PROJECT --no-browser` on :8765.
// `npm run build` writes the bundle to ../static, which the Python server serves.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: { outDir: "../static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
