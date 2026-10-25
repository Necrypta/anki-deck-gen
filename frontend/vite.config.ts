import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The build label CI stamps into ankigen/_build.py before building the UI, so
// the app can tell when its window is showing a UI from a different build.
function buildLabel(): string {
  try {
    const src = readFileSync(new URL("../ankigen/_build.py", import.meta.url), "utf8");
    return JSON.parse(/^BUILD = (".*")$/m.exec(src)?.[1] ?? '"dev"');
  } catch {
    return "dev";
  }
}

export default defineConfig({
  plugins: [react()],
  define: { __UI_BUILD__: JSON.stringify(buildLabel()) },
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
