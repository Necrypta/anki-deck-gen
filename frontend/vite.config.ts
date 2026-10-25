import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Relative asset paths so the build loads from file:// inside pywebview.
  base: "./",
  server: {
    port: 5173,
    strictPort: true,
    // In a plain browser, API calls go to `python -m ankigen.devserver`.
    proxy: { "/api": "http://127.0.0.1:5174" },
  },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1500 },
});
