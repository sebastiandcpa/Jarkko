import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        app: fileURLToPath(new URL("./index.html", import.meta.url)),
        concepts: fileURLToPath(new URL("./concepts.html", import.meta.url)),
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    watch: { ignored: ["**/release/**", "**/dist/**"] },
  },
});
