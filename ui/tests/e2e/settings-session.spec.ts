import { expect, test as base } from '@playwright/test';
import {
  apiBaseUrl,
  bootstrapEnvironment,
  BootstrapResult,
  shouldRun,
} from './support';

const test = base.extend<{ bootstrap: BootstrapResult }>({
  bootstrap: [
    async ({}, use) => {
      const bootstrap = await bootstrapEnvironment();
      await use(bootstrap);
    },
    { scope: 'worker' },
  ],
});

test.describe('Settings credential flows', () => {
  test('imports and clears the ChatGPT session bundle', async ({ page, request, bootstrap }) => {
    test.skip(!shouldRun, 'Set ENABLE_CI_E2E_UI=1 to run the UI smoke suite');
    void bootstrap;

    const clearResponse = await request.delete(`${apiBaseUrl}/integrations/pat/session`, {
      data: { updated_by: 'playwright-e2e' },
    });
    expect(clearResponse.ok()).toBeTruthy();

    await page.goto('/settings');

    const sessionStatusLabel = page
      .locator('.credential-card-header', { hasText: 'ChatGPT Session Bundle' })
      .locator('.status-badge-label');

    await expect(sessionStatusLabel).toHaveText(/Missing/i);

    const bundlePayload = {
      session_token: `playwright-session-${Date.now()}`,
      expires_at: new Date(Date.now() + 86_400_000).toISOString(),
      user_agent: 'Playwright Test Runner',
    };
    const bundleJson = JSON.stringify(bundlePayload);

    await page.getByLabel('Session Bundle JSON').fill(bundleJson);

    const importResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/integrations/pat/session') &&
        response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Import Session' }).click();
    const importResult = await importResponse;
    expect(importResult.ok()).toBeTruthy();

    await expect(page.getByText('ChatGPT session bundle imported successfully.', { exact: true })).toBeVisible();
    await expect(sessionStatusLabel).toHaveText(/Active/i);

    const clearButton = page.getByRole('button', { name: 'Clear Session' });
    await expect(clearButton).toBeEnabled();
    await clearButton.click();

    const modal = page.locator('.modal');
    await expect(modal).toBeVisible();

    const clearModalResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/integrations/pat/session') &&
        response.request().method() === 'DELETE',
    );
    await modal.getByRole('button', { name: 'Clear Session' }).click();
    const clearResult = await clearModalResponse;
    expect(clearResult.ok()).toBeTruthy();

    await expect(page.getByText('ChatGPT session bundle cleared. Import a fresh bundle to continue.', { exact: true })).toBeVisible();
    await expect(sessionStatusLabel).toHaveText(/Missing/i);
  });
});
