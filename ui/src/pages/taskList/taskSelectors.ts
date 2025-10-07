import { CodexModel, ConcurrencySettings, Project, TaskStatus } from '../../types';
import { TaskFilters } from './types';

export type ProjectLookup = Map<number, Project>;

export function buildProjectLookup(projects: Project[]): ProjectLookup {
  const lookup: ProjectLookup = new Map();
  projects.forEach((project) => {
    lookup.set(project.id, project);
  });
  return lookup;
}

export function getProjectDisplayName(lookup: ProjectLookup, projectId: number): string {
  const project = lookup.get(projectId);
  return project ? project.name : `Project ${projectId}`;
}

export function getProjectForTask(lookup: ProjectLookup, projectId: number): Project | null {
  return lookup.get(projectId) ?? null;
}

export function getCodexModelLabel(models: CodexModel[], modelId: string | null | undefined): string {
  if (!modelId) {
    return '--';
  }
  const model = models.find((candidate) => candidate.id === modelId);
  return model?.label ?? modelId;
}

const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
  aborted: 'Aborted',
};

export function formatTaskStatus(status: TaskStatus): string {
  return TASK_STATUS_LABELS[status];
}

export function isTaskActive(status: TaskStatus): boolean {
  return status === 'pending' || status === 'running';
}

export function formatReasoningEffort(value: string | null | undefined): string {
  if (!value) {
    return 'Medium';
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function normalizeTaskFilters(filters: TaskFilters): TaskFilters {
  const uniqueStatuses = Array.from(new Set(filters.statuses));
  return {
    statuses: uniqueStatuses,
    codexModel: filters.codexModel.trim(),
    branch: filters.branch.trim(),
  };
}

export function hasActiveFilters(filters: TaskFilters): boolean {
  return Boolean(filters.branch) || Boolean(filters.codexModel) || filters.statuses.length > 0;
}

export function areFiltersEqual(a: TaskFilters, b: TaskFilters): boolean {
  if (a.codexModel !== b.codexModel || a.branch !== b.branch) {
    return false;
  }
  if (a.statuses.length !== b.statuses.length) {
    return false;
  }
  const set = new Set(a.statuses);
  return b.statuses.every((value) => set.has(value));
}

type ConcurrencyBannerState = {
  totalActive: number;
  projectsAtLimit: Project[];
  effectiveLimit: number | null;
};

export function computeConcurrencyBannerState(
  projects: Project[],
  settings: ConcurrencySettings | null,
): ConcurrencyBannerState {
  const effectiveLimit = settings?.effective_project_limit ?? null;
  const limit = typeof effectiveLimit === 'number' && effectiveLimit > 0 ? effectiveLimit : null;
  const projectsAtLimit = limit
    ? projects.filter((project) => typeof project.active_task_count === 'number' && project.active_task_count >= limit)
    : [];
  const totalActive = projects.reduce((acc, project) => acc + (project.active_task_count ?? 0), 0);

  return { totalActive, projectsAtLimit, effectiveLimit: limit };
}
