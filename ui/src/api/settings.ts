import { request } from './client';
import { ConcurrencySettings, ConcurrencySettingsUpdatePayload } from '../types';

export function getConcurrencySettings(): Promise<ConcurrencySettings> {
  return request<ConcurrencySettings>('/settings/concurrency');
}

export function updateConcurrencySettings(payload: ConcurrencySettingsUpdatePayload): Promise<ConcurrencySettings> {
  return request<ConcurrencySettings>('/settings/concurrency', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
