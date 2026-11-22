/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("../", import.meta.url));

// Ports come from the project-level .env (one folder up) so backend and frontend agree on both OSes.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, projectRoot, "");
  const backendPort = Number(env.BACKEND_PORT || 8765);
  const frontendPort = Number(env.FRONTEND_PORT || 5173);
  const bindHost = env.BACKEND_HOST || "127.0.0.1";
  const backendHost = bindHost === "0.0.0.0" ? "127.0.0.1" : bindHost === "::" ? "::1" : bindHost;
  const urlHost = backendHost.includes(":") ? `[${backendHost}]` : backendHost;
  const proxy = { "/api": { target: `http://${urlHost}:${backendPort}`, changeOrigin: false } };
  return {
    plugins: [react()],
    envDir: projectRoot,
    // Separate dependency-optimizer caches let a dev server and the E2E server run side by side safely.
    cacheDir: env.VITE_CACHE_DIR || "node_modules/.vite",
    server: {
      host: "127.0.0.1",
      port: frontendPort,
      strictPort: true,
      proxy,
    },
    preview: {
      host: "127.0.0.1",
      port: frontendPort,
      proxy,
    },
    build: { outDir: "dist", sourcemap: false },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      include: ["src/**/*.test.{ts,tsx}"],
    },
  };
});
