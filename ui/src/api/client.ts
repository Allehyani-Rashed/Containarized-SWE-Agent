export class ApiError extends Error {
  status: number;
  payload: unknown;

  constructor(message: string, status: number, payload: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

type FetchInput = Parameters<typeof fetch>[0];
type FetchInit = Parameters<typeof fetch>[1];

export async function request<T>(input: FetchInput, init: FetchInit = {}): Promise<T> {
  const response = await fetch(input, init);
  const contentType = response.headers.get('content-type') ?? '';
  const isJson = contentType.includes('application/json');

  const parseBody = async () => {
    if (!isJson) {
      return null;
    }
    try {
      return await response.json();
    } catch (error) {
      return null;
    }
  };

  if (!response.ok) {
    const payload = await parseBody();
    const message =
      (payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail?: unknown }).detail)
        : null) || response.statusText || 'Request failed';
    throw new ApiError(message, response.status, payload);
  }

  if (!isJson) {
    return undefined as T;
  }

  const data = await parseBody();
  return data as T;
}
