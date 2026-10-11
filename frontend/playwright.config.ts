import { defineConfig } from '@playwright/test'

const integrationURL = process.env.FRONTEND_BASE_URL

export default defineConfig({
  testDir: './tests',
  testMatch: integrationURL ? 'integration.spec.ts' : ['app.spec.ts', 'accessibility.spec.ts'],
  fullyParallel: true,
  workers: 2,
  retries: 0,
  reporter: 'list',
  outputDir: integrationURL ? 'test-results/integration' : 'test-results/frontend',
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
  use: {
    baseURL: integrationURL ?? 'http://127.0.0.1:4173',
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: integrationURL
    ? undefined
    : {
        command: 'pnpm preview',
        stderr: 'ignore',
        url: 'http://127.0.0.1:4173',
        reuseExistingServer: false,
      },
})
