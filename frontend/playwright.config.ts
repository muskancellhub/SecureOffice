import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e/tests',
  outputDir: './e2e/test-results',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 180000, // 🔥 3 minutes - increased for AI design generation in beforeAll hooks
  
  // 🔥 Global hooks for evidence collection
  globalSetup: undefined,
  globalTeardown: undefined,
  
  reporter: [
    ['html', { outputFolder: './e2e/playwright-report', open: 'never' }],
    ['list'],
    ['json', { outputFile: './e2e/test-results/test-results.json' }],
  ],

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on',  // 🔥 Capture full trace for ALL tests
    screenshot: 'on',  // 🔥 Take screenshots for ALL tests
    video: 'on',  // 🔥 Record videos for ALL tests
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
  },

  projects: [
    // Auth setup — runs first
    {
      name: 'auth-setup',
      testMatch: /auth\.setup\.ts/,
    },

    // Main browser tests
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['auth-setup'],
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
      dependencies: ['auth-setup'],
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
      dependencies: ['auth-setup'],
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
