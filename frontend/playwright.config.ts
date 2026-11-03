import { defineConfig, devices } from '@playwright/test'

// Browser checks that replay a labelled FIXTURE response (e2e/fixtures/). They need
// no backend: the analyze request is intercepted. Results are fixture results only.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  fullyParallel: false,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:5174',
    viewport: { width: 1366, height: 860 },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npx vite --port 5174 --strictPort',
    url: 'http://localhost:5174',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
