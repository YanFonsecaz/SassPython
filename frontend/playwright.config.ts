import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: 0,
  use: {
    baseURL: "http://localhost:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
  webServer: [
    {
      command: "cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port 8000",
      port: 8000,
      reuseExistingServer: true,
      timeout: 30000,
    },
    {
      command: "npx next dev --port 3000",
      port: 3000,
      reuseExistingServer: true,
      timeout: 30000,
    },
  ],
});
