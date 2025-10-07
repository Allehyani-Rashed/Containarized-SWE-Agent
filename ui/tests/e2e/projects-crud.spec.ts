import { expect, test as base } from '@playwright/test';
import {
  apiBaseUrl,
  bootstrapEnvironment,
  BootstrapResult,
  codexScriptPath,
  defaultBranch,
  execFileAsync,
  gitlabHost,
  pythonBin,
  repoRoot,
  shouldRun,
} from './support';

type ProjectBootstrapResult = {
  project: {
    id: number;
    name: string;
    default_branch: string;
    gitlab_host: string;
    gitlab_project_path: string;
    allowlist: string[];
    allowlist_status: string;
  };
};

async function runProjectBootstrap(options: {
  projectName: string;
  gitlabHost: string;
  projectPath: string;
  defaultBranch: string;
  allowlist?: string[];
}): Promise<ProjectBootstrapResult> {
  const args = [
    'projects',
    'bootstrap',
    '--api-base',
    apiBaseUrl,
    '--project-name',
    options.projectName,
    '--gitlab-host',
    options.gitlabHost,
    '--project-path',
    options.projectPath,
    '--default-branch',
    options.defaultBranch,
    '--actor',
    'playwright-e2e',
  ];

  if (options.allowlist && options.allowlist.length > 0) {
    args.push('--allowlist', options.allowlist.join(','));
  }

  args.push('--json');

  const { stdout } = await execFileAsync(pythonBin, [codexScriptPath, ...args], {
    cwd: repoRoot,
    env: {
      ...process.env,
      RUNNER_GIT_DRY_RUN: '0',
    },
    encoding: 'utf-8',
  });

  const payload = stdout.trim();
  if (!payload) {
    throw new Error('codex projects bootstrap returned empty output');
  }
  const parsed = JSON.parse(payload) as ProjectBootstrapResult;
  return parsed;
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

test.describe('Projects CRUD coverage', () => {
  test('creates, updates, and deletes a project with UI validation', async ({ page, request, bootstrap }) => {
    test.skip(!shouldRun, 'Set ENABLE_CI_E2E_UI=1 to run the UI smoke suite');

    const host = (bootstrap.project.gitlab_host || gitlabHost || '').trim();
    if (!host) {
      throw new Error('GitLab host is required to exercise project CRUD flows');
    }

    const uniqueId = Date.now();
    const initialName = `[E2E] Playwright CRUD ${uniqueId}`;
    const updatedName = `${initialName} Updated`;
    const projectPathSlug = `playwright/e2e-crud-${uniqueId}`;
    const initialBranch = defaultBranch || 'main';

    const createResult = await runProjectBootstrap({
      projectName: initialName,
      gitlabHost: host,
      projectPath: projectPathSlug,
      defaultBranch: initialBranch,
    });
    const projectId = createResult.project.id;

    await page.goto('/projects');

    const searchInput = page.getByPlaceholder('Search by name, repository, or host...');
    await searchInput.fill(initialName);

    const projectCard = page.locator('.project-card').filter({
      has: page.getByRole('heading', { level: 3, name: initialName }),
    });

    await expect(projectCard).toBeVisible();
    await expect(projectCard).toContainText(initialBranch);
    await expect(projectCard.getByText('Default only')).toBeVisible();

    const updatedBranch = 'develop';
    const allowlist = ['example.com', 'docs.example.com'];

    await runProjectBootstrap({
      projectName: updatedName,
      gitlabHost: host,
      projectPath: projectPathSlug,
      defaultBranch: updatedBranch,
      allowlist,
    });

    await page.reload();
    await searchInput.fill(updatedName);

    const updatedCard = page.locator('.project-card').filter({
      has: page.getByRole('heading', { level: 3, name: updatedName }),
    });

    await expect(updatedCard).toBeVisible();
    await expect(updatedCard).toContainText(updatedBranch);
    await expect(updatedCard.getByText('2 domains')).toBeVisible();

    const deleteResponse = await request.delete(`${apiBaseUrl}/projects/${projectId}`, {
      data: { actor: 'playwright-e2e' },
    });
    expect(deleteResponse.ok()).toBeTruthy();

    await page.reload();
    await searchInput.fill(updatedName);

    await expect(page.getByText('No matching projects')).toBeVisible();
  });
});
