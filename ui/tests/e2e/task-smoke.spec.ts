import { expect, test as base } from '@playwright/test';
import {
  apiBaseUrl,
  bootstrapEnvironment,
  BootstrapResult,
  defaultBranch,
  gitlabHost,
  shouldRun,
} from './support';

type TaskRecord = {
  id: number;
  status: 'pending' | 'running' | 'done' | 'failed' | 'aborted';
  prompt: string;
  branch: string | null;
  target_branch: string | null;
  codex_model: string | null;
  codex_reasoning_effort: string | null;
  mr_url: string | null;
  change_mode: 'merge_request' | 'branch_commit';
  commit_sha: string | null;
  commit_url: string | null;
};

type TaskLogSnapshot = {
  task_id: number;
  entries: string[];
  status: TaskRecord['status'];
  branch: string | null;
  target_branch: string | null;
  codex_model: string | null;
  codex_reasoning_effort: string | null;
  abort_requested: boolean;
  change_mode: TaskRecord['change_mode'];
  commit_sha: string | null;
  commit_url: string | null;
};

type BranchListResponse = {
  items: Array<{ name: string; default?: boolean }>;
  next_page: number | null;
};

function stubBranches(branchName: string): BranchListResponse {
  return {
    items: [
      {
        name: branchName,
        default: true,
      },
    ],
    next_page: null,
  };
}

const test = base.extend<{ bootstrap: BootstrapResult }>({
  bootstrap: [
    async ({}, use) => {
      const bootstrap = await bootstrapEnvironment();
      await use(bootstrap);
    },
    { scope: 'worker' },
  ],
});

test.describe('Task smoke suite', () => {
  test.beforeEach(async ({ page, bootstrap }) => {
    if (!shouldRun) {
      test.skip(true, 'Set ENABLE_CI_E2E_UI=1 to run the UI smoke suite');
    }
    const branchName = bootstrap.project.default_branch || defaultBranch;
    await page.route('**/projects/*/branches**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(stubBranches(branchName)),
      });
    });
  });

  test('Submit Task dashboard surfaces seeded project and credentials', async ({ page, bootstrap }) => {
    test.skip(!shouldRun, 'Set ENABLE_CI_E2E_UI=1 to run the UI smoke suite');
    const { project } = bootstrap;
    const branchName = project.default_branch || defaultBranch;

    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'Submit Task' })).toBeVisible();

    const projectSelect = page.getByLabel('Project');
    await expect(projectSelect).toContainText(project.name);
    await projectSelect.selectOption({ value: String(project.id) });
    await expect(projectSelect).toHaveValue(String(project.id));

    const branchInput = page.getByLabel('Base Branch');
    await expect(branchInput).toHaveValue(branchName);

    const summaryList = page.locator('.summary-list').first();
    await expect(summaryList).toContainText('GitLab PAT');
    await expect(summaryList).toContainText('Configured');
    await expect(summaryList).toContainText(project.name);
  });

  test('Projects dashboard lists the automation project', async ({ page, bootstrap }) => {
    test.skip(!shouldRun, 'Set ENABLE_CI_E2E_UI=1 to run the UI smoke suite');
    const { project } = bootstrap;

    await page.goto('/');
    await page.getByRole('link', { name: 'Projects' }).click();

    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.locator('main')).toContainText(project.name);
    await expect(page.locator('main')).toContainText((project.gitlab_host || gitlabHost).replace(/^https?:\/\//, ''));
  });

  test('Task submission surfaces streamed logs and merge request metadata', async ({ page, request, bootstrap }) => {
    test.skip(!shouldRun, 'Set ENABLE_CI_E2E_UI=1 to run the UI smoke suite');
    const { project } = bootstrap;
    const timestamp = Date.now();
    const prompt = `Playwright smoke log stream ${timestamp}`;
    const mrTitle = `Playwright smoke MR ${timestamp}`;
    const baseBranchOverride = `feature/playwright-${timestamp}`;

    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Submit Task' })).toBeVisible();

    await page.getByLabel('Project').selectOption({ value: String(project.id) });
    const baseBranchInput = page.getByLabel('Base Branch');
    await baseBranchInput.fill(baseBranchOverride);
    await page.getByLabel('Merge Request Title').fill(mrTitle);
    await page.getByLabel('Prompt').fill(prompt);

    const createResponse = page.waitForResponse(
      (response) => response.url().endsWith('/tasks') && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Create Task' }).click();
    const createPayload = await createResponse;

    expect(createPayload.ok()).toBeTruthy();

    const createdTask = (await createPayload.json()) as TaskRecord;
    const taskId = createdTask.id;

    const successNotice = page.locator('.notice.notice-success');
    await expect(successNotice).toContainText(`Task ${taskId} created.`);
    await page.getByRole('button', { name: `View Task ${taskId}` }).click();

    await expect(page).toHaveURL(/\/tasks$/);
    await expect(page.getByRole('heading', { name: 'Credential Status' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Concurrency & Worker Pool' })).toBeVisible();

    const taskRow = page
      .locator('.task-table tbody tr')
      .filter({ hasText: String(taskId) })
      .first();
    await expect(taskRow).toContainText(baseBranchOverride);

    await page.getByRole('button', { name: 'Open task drawer' }).click();
    await expect(page.getByRole('heading', { name: 'Task Detail', level: 3 })).toBeVisible();
    await expect(page.locator('.task-drawer')).toContainText(`Task #${taskId}`);
    await expect(page.locator('.drawer-meta-grid')).toContainText(baseBranchOverride);

    const deadline = Date.now() + 180_000;
    let detail: TaskRecord | null = null;
    // Poll task detail until it exits the pending/running states.
    do {
      const detailResponse = await request.get(`${apiBaseUrl}/tasks/${taskId}`);
      expect(detailResponse.ok()).toBeTruthy();
      detail = (await detailResponse.json()) as TaskRecord;
      if (!['pending', 'running'].includes(detail.status)) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1_000));
    } while (Date.now() < deadline);

    if (!detail || ['pending', 'running'].includes(detail.status)) {
      throw new Error(`Task ${taskId} did not finish in time; last status ${(detail && detail.status) || 'unknown'}`);
    }

    expect(['done', 'failed'].includes(detail.status)).toBeTruthy();

    if (detail.status === 'done') {
      expect(detail.mr_url).toBeTruthy();
    }

    const logsResponse = await request.get(`${apiBaseUrl}/tasks/${taskId}/logs?follow=0`);
    expect(logsResponse.ok()).toBeTruthy();
    const logsPayload = (await logsResponse.json()) as TaskLogSnapshot;
    expect(logsPayload.entries.length).toBeGreaterThan(0);
    const logOutput = page.locator('.task-drawer .log-output');
    await expect(logOutput).toContainText(/Codex|Unable to decrypt/i, { timeout: 60_000 });
    await expect(page.locator('.logs-metadata')).toContainText('Status at capture');

    if (detail.mr_url) {
      await expect(page.locator(`.task-drawer a[href="${detail.mr_url}"]`)).toBeVisible();
    }
  });

  test('Settings allows verifying the PAT', async ({ page }) => {
    test.skip(!shouldRun, 'Set ENABLE_CI_E2E_UI=1 to run the UI smoke suite');
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Credentials & Integrations' })).toBeVisible();

    const verifyButton = page.getByRole('button', { name: /Verify PAT access/i });
    await expect(verifyButton).toBeEnabled();
    await verifyButton.click();

    const verifyNotice = page.locator('.notice').first();
    await expect(verifyNotice).toBeVisible();
    await expect(verifyNotice).toContainText(/PAT verified against|Unauthorized/i);
  });
});
