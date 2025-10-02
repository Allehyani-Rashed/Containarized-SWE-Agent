import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

const isCI = process.env.CI === '1' || process.env.CI === 'true';
const apiBaseUrl = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8000';
const uiBaseUrl = process.env.E2E_UI_BASE_URL ?? 'http://127.0.0.1:5173';
const pythonBin = process.env.E2E_PYTHON_BIN ?? 'python3';
const currentFile = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(currentFile), '..');

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  timeout: 5 * 60 * 1000,
  expect: {
    timeout: 15_000,
  },
  retries: isCI ? 1 : 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  outputDir: 'test-results',
  use: {
    baseURL: uiBaseUrl,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: isCI ? 'retain-on-failure' : 'on-first-retry',
    extraHTTPHeaders: {
      'X-E2E-Test': 'ui-playwright',
    },
  },
  workers: isCI ? 2 : undefined,
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: `bash -lc "cd app && ${pythonBin} -m uvicorn app.main:app --host 127.0.0.1 --port 8000"`,
      url: `${apiBaseUrl.replace(/\/$/, '')}/healthz`,
      reuseExistingServer: !isCI,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 120_000,
      cwd: repoRoot,
    },
    {
      command: 'bash -lc "unset npm_config_prefix && cd ui && npm run dev -- --host 127.0.0.1 --port 5173"',
      url: uiBaseUrl,
      reuseExistingServer: !isCI,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 120_000,
      cwd: repoRoot,
    },
  ],
});
