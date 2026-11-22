import { defineConfig } from "@playwright/test";

// E2E builds the frontend and lets an isolated backend serve it (port 8766, its own SQLite file
// data/local/e2e.db). This tests the production bundle, needs no Vite dev server, and never touches the
// user's demo database. On Windows the installed Microsoft Edge is used (no browser download needed);
// elsewhere Playwright's Chromium is used (`npx playwright install chromium`).
// Override with PW_CHANNEL=chrome|msedge|chromium.
// Ordinary browser tests use the labelled fallback, including when a local .env configures a model.
const isWin = process.platform === "win32";
const python = process.env.E2E_PYTHON ?? (isWin ? "../.venv/Scripts/python.exe" : "../.venv/bin/python");
const channel = process.env.PW_CHANNEL === "chromium" ? undefined : process.env.PW_CHANNEL ?? (isWin ? "msedge" : undefined);
const PORT = process.env.E2E_BACKEND_PORT ?? "8766";

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts/,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    viewport: { width: 1440, height: 900 },
    channel,
    trace: "off",
  },
  webServer: {
    command: `node node_modules/vite/bin/vite.js build --logLevel warn && "${python}" -m uvicorn app.main:app --app-dir ../backend --host 127.0.0.1 --port ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    env: {
      CSC2524_DB_PATH: "data/local/e2e.db",
      BACKEND_PORT: PORT,
      ...(process.env.REAL_AI === "1" ? {} : { OLLAMA_MODEL: "" }),
    },
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
