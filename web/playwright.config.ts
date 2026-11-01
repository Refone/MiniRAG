import { defineConfig } from "@playwright/test";

/** mock API 端口（与 e2e/mock-server/server.mjs 默认值一致） */
const MOCK_PORT = 4000;
/** 测试专用前端端口：避开人类日常 dev server 的 5173 */
const APP_PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  globalTimeout: 30 * 60 * 1000,
  timeout: 30_000,
  expect: { timeout: 7_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${APP_PORT}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // 关掉动效：布局断言不被过渡动画干扰
    reducedMotion: "reduce",
  },
  webServer: [
    {
      command: "node e2e/mock-server/server.mjs",
      port: MOCK_PORT,
      env: { MOCK_PORT: String(MOCK_PORT) },
      reuseExistingServer: !process.env.CI,
      timeout: 15_000,
    },
    {
      // 前端直连 mock（VITE_API_BASE）：契约完全由 mock 决定，不依赖真实后端
      command: `npx vite --port ${APP_PORT} --strictPort --host 127.0.0.1`,
      env: { VITE_API_BASE: `http://127.0.0.1:${MOCK_PORT}` },
      port: APP_PORT,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "desktop-chromium",
      grepInvert: /@mobile/,
      use: { browserName: "chromium", viewport: { width: 1280, height: 800 } },
    },
    {
      name: "mobile-chromium",
      grep: /@mobile/,
      use: {
        browserName: "chromium",
        viewport: { width: 390, height: 844 },
        hasTouch: true,
      },
    },
  ],
});
