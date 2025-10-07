import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

export type ProjectRecord = {
  id: number;
  name: string;
  default_branch: string;
  gitlab_host: string;
  gitlab_project_path: string;
  allowlist?: string[];
};

export type PatStatus = {
  configured: boolean;
  session_configured?: boolean;
};

export type BootstrapResult = {
  project: ProjectRecord;
  pat: PatStatus;
  allowlist: string[];
};

export const apiBaseUrl = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8000';
export const gitlabHost = process.env.E2E_GITLAB_HOST ?? '';
export const projectPath = process.env.E2E_GITLAB_PROJECT_PATH ?? '';
export const defaultBranch = process.env.E2E_DEFAULT_TARGET_BRANCH ?? 'main';
export const projectName = process.env.E2E_PROJECT_NAME ?? '[E2E] Playwright Smoke Project';
export const sessionBundlePath =
  process.env.CHATGPT_SESSION_BUNDLE_PATH ?? process.env.E2E_CHATGPT_SESSION_BUNDLE_PATH ?? '';
export const sessionBundleJson =
  process.env.CHATGPT_SESSION_JSON ?? process.env.E2E_CHATGPT_SESSION_JSON ?? '';

export const pythonBin = process.env.E2E_PYTHON_BIN ?? 'python3';
const currentFile = fileURLToPath(import.meta.url);
export const repoRoot = path.resolve(path.dirname(currentFile), '..', '..', '..');
export const codexScriptPath = path.join(repoRoot, 'scripts', 'codex');
export const runnerGitDryRun = process.env.RUNNER_GIT_DRY_RUN ?? '0';
export const bootstrapDryRun = process.env.E2E_BOOTSTRAP_DRY_RUN ?? runnerGitDryRun ?? '0';
export const fallbackGitlabPat =
  process.env.E2E_GITLAB_PAT ?? process.env.GITLAB_PAT ?? 'sk-test-playwright';

export const execFileAsync = promisify(execFile);

export const shouldRun = (() => {
  const flag = process.env.ENABLE_CI_E2E_UI ?? '';
  return ['1', 'true', 'yes'].includes(flag.toLowerCase());
})();

export async function bootstrapEnvironment(): Promise<BootstrapResult> {
  const args = [
    'projects',
    'bootstrap',
    '--api-base',
    apiBaseUrl,
    '--project-name',
    projectName,
    '--actor',
    'playwright-e2e',
  ];

  if (gitlabHost) {
    args.push('--gitlab-host', gitlabHost);
  }
  if (projectPath) {
    args.push('--project-path', projectPath);
  }
  if (defaultBranch) {
    args.push('--default-branch', defaultBranch);
  }
  if (process.env.E2E_UI_BASE_URL) {
    args.push('--ui-base-url', process.env.E2E_UI_BASE_URL);
  }
  if (sessionBundlePath) {
    args.push('--session-bundle-path', sessionBundlePath);
  } else if (sessionBundleJson) {
    args.push('--session-bundle', sessionBundleJson);
  }

  if (!process.env.E2E_GITLAB_PAT && !process.env.GITLAB_PAT) {
    args.push('--gitlab-pat', fallbackGitlabPat);
  }

  const projectPat = process.env.E2E_GITLAB_PAT ?? process.env.GITLAB_PAT ?? '';
  if (projectPat) {
    args.push('--project-pat', projectPat);
  }

  args.push('--json');

  const { stdout } = await execFileAsync(pythonBin, [codexScriptPath, ...args], {
    cwd: repoRoot,
    env: {
      ...process.env,
      RUNNER_GIT_DRY_RUN: bootstrapDryRun,
    },
    encoding: 'utf-8',
  });

  const payload = stdout.trim();
  if (!payload) {
    throw new Error('codex projects bootstrap returned empty output');
  }

  try {
    return JSON.parse(payload) as BootstrapResult;
  } catch (error) {
    throw new Error(`Failed to parse bootstrap output: ${(error as Error).message}. Raw output: ${payload}`);
  }
}
