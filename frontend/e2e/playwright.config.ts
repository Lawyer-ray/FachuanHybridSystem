import { defineConfig, devices } from '@playwright/test';

/**
 * 前端 E2E 测试配置（Playwright TypeScript）
 *
 * 注意：前端 UI 尚未定型，当前仅搭建框架，暂不编写测试用例。
 * 待前端稳定后，在 tests/ 目录下添加 *.spec.ts 文件即可运行。
 *
 * 运行方式：
 *   cd frontend
 *   npx playwright test                 # 无头模式
 *   npx playwright test --headed        # 有头模式
 *   npx playwright test --ui            # Playwright UI 模式
 */
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  /* 前端 dev server 配置（取消注释以自动启动） */
  // webServer: {
  //   command: 'npm run dev',
  //   url: 'http://localhost:5173',
  //   reuseExistingServer: !process.env.CI,
  // },
});
