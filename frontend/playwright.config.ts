import { defineConfig } from "@playwright/test";

// End-to-end tests drive the real backend and the Vite dev server.
// In this environment Chromium is preinstalled; elsewhere run `npx playwright install chromium`
// and unset PLAYWRIGHT_CHROMIUM.
const chromium = process.env.PLAYWRIGHT_CHROMIUM ?? (process.env.PLAYWRIGHT_BROWSERS_PATH ? `${process.env.PLAYWRIGHT_BROWSERS_PATH}/chromium-1194/chrome-linux/chrome` : undefined);

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  expect: { timeout: 20_000 },
  workers: 1,
  retries: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5173",
    launchOptions: { executablePath: chromium, args: ["--headless=new"] },
    trace: "retain-on-failure",
  },
  webServer: [
    { command: "cd ../backend && RESQNET_DB=$(mktemp -u /tmp/resqnet-e2e-XXXXXX.db) python -m uvicorn app.api.main:app --port 8000", url: "http://localhost:8000/api/health", reuseExistingServer: true, timeout: 60_000 },
    { command: "npx vite --port 5173 --strictPort", url: "http://localhost:5173", reuseExistingServer: true, timeout: 60_000 },
  ],
});
