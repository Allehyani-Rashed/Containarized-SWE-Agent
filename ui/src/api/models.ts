import { CodexModel } from '../types';
import { request } from './client';

export function listCodexModels(): Promise<CodexModel[]> {
  return request<CodexModel[]>('/models');
}
