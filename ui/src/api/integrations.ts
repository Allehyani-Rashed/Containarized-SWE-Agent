import {
  PatClearPayload,
  PatStatus,
  PatStorePayload,
  PatVerifyPayload,
  SessionClearPayload,
  SessionPayload,
} from '../types';
import { request } from './client';

type PatStatusResponse = Partial<PatStatus> & {
  configured?: boolean;
  updated_at?: string | null;
  updated_by?: string | null;
  session_configured?: boolean;
  session_updated_at?: string | null;
  session_updated_by?: string | null;
  active_credential?: 'session' | 'none';
  verification_status?: 'verified' | 'error' | null;
  verification_checked_at?: string | null;
  verification_error?: string | null;
  verification_host?: string | null;
};

export const initialPatStatus: PatStatus = {
  configured: false,
  updated_at: null,
  updated_by: null,
  session_configured: false,
  session_updated_at: null,
  session_updated_by: null,
  active_credential: 'none',
  verification_status: null,
  verification_checked_at: null,
  verification_error: null,
  verification_host: null,
};

export function mapPatStatus(data: PatStatusResponse): PatStatus {
  return {
    configured: data.configured ?? false,
    updated_at: data.updated_at ?? null,
    updated_by: data.updated_by ?? null,
    session_configured: data.session_configured ?? false,
    session_updated_at: data.session_updated_at ?? null,
    session_updated_by: data.session_updated_by ?? null,
    active_credential: data.active_credential ?? 'none',
    verification_status: data.verification_status ?? null,
    verification_checked_at: data.verification_checked_at ?? null,
    verification_error: data.verification_error ?? null,
    verification_host: data.verification_host ?? null,
  };
}

function jsonRequestInit(body: unknown): Parameters<typeof fetch>[1] {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  };
}

export async function getPatStatus(): Promise<PatStatus> {
  const data = await request<PatStatusResponse>('/integrations/pat');
  return mapPatStatus(data);
}

export async function storePat(payload: PatStorePayload): Promise<PatStatus> {
  const data = await request<PatStatusResponse>('/integrations/pat', jsonRequestInit(payload));
  return mapPatStatus(data);
}

export async function clearPat(payload: PatClearPayload): Promise<PatStatus> {
  const data = await request<PatStatusResponse>('/integrations/pat', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return mapPatStatus(data);
}

export async function verifyPat(payload: PatVerifyPayload): Promise<PatStatus> {
  const data = await request<PatStatusResponse>('/integrations/pat/verify', jsonRequestInit(payload));
  return mapPatStatus(data);
}

export async function importSession(payload: SessionPayload): Promise<PatStatus> {
  const data = await request<PatStatusResponse>('/integrations/pat/session', jsonRequestInit(payload));
  return mapPatStatus(data);
}

export async function clearSession(payload: SessionClearPayload): Promise<PatStatus> {
  const data = await request<PatStatusResponse>('/integrations/pat/session', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return mapPatStatus(data);
}
