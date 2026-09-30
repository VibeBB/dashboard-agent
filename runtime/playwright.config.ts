import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: join(tmpdir(), "dashboard-playwright-results"),
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4173",
    browserName: "chromium",
    headless: true,
  },
  webServer: {
    command: "node e2e/serve.mjs",
    url: "http://127.0.0.1:4173/health",
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [
    {
      name: "chromium",
      testMatch: ["dashboard.spec.ts", "webmcp-disabled.spec.ts", "tauri.spec.ts"],
    },
    {
      name: "chromium-webmcp",
      testMatch: ["webmcp.spec.ts"],
      use: { launchOptions: { args: ["--enable-features=WebMCPTesting"] } },
    },
  ],
});
