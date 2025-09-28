import {
  Project,
  ProjectCreatePayload,
  ProjectDeletePayload,
  ProjectDetail,
  ProjectUpdatePayload,
} from '../types';
import { request } from './client';

export function listProjects(): Promise<Project[]> {
  return request<Project[]>('/projects');
}

export function createProject(payload: ProjectCreatePayload): Promise<Project> {
  return request<Project>('/projects', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function getProject(projectId: number): Promise<ProjectDetail> {
  return request<ProjectDetail>(`/projects/${projectId}`);
}

export function updateProject(projectId: number, payload: ProjectUpdatePayload): Promise<Project> {
  return request<Project>(`/projects/${projectId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function deleteProject(projectId: number, payload?: ProjectDeletePayload): Promise<void> {
  return request(`/projects/${projectId}`, {
    method: 'DELETE',
    headers: payload ? { 'Content-Type': 'application/json' } : undefined,
    body: payload ? JSON.stringify(payload) : undefined,
  });
}
