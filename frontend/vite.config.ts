import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" keeps the build portable (can be opened from file:// or served).
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5173, host: true },
  build: { outDir: "dist", emptyOutDir: true },
});
