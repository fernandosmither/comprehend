import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the SPA runs on :5173 and proxies API + connector paths to the backend (:8793),
// so the browser sees one origin and the session cookie just works. Prod: the Python
// app serves the built assets, so everything is same-origin there too.
export default defineConfig({
  plugins: [react()],
  base: "/",
  build: { outDir: "dist", emptyOutDir: true },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8793",
      "/health": "http://127.0.0.1:8793",
      "/c": "http://127.0.0.1:8793",
      "/owner": "http://127.0.0.1:8793",
    },
  },
});
