// API base URL from environment
export const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

// User-friendly error messages
const ERROR_MESSAGES: Record<number, string> = {
  401: 'Session expired. Please verify your credentials in Settings.',
  403: 'Access denied. Check your GitLab Personal Access Token scopes in Settings.',
  404: 'The requested resource was not found.',
  408: 'Request timeout. Please check your connection and try again.',
  429: 'Too many requests. Please wait a moment and try again.',
  500: 'Server error. The system is experiencing issues. Please try again.',
  502: 'Bad gateway. The server is temporarily unavailable.',
  503: 'Service unavailable. The server is temporarily down for maintenance.',
  504: 'Gateway timeout. The request took too long to complete.',
};

export class ApiError extends Error {
  status: number;
  payload: unknown;
  isRetryable: boolean;

  constructor(message: string, status: number, payload: unknown, isRetryable = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
    this.isRetryable = isRetryable;
  }
}

type FetchInput = Parameters<typeof fetch>[0];
type FetchInit = Parameters<typeof fetch>[1];

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

const isRetryableError = (status: number | null): boolean => {
  // Retry on 5xx errors and network failures (null status)
  return status === null || status >= 500;
};

const getUserFriendlyMessage = (status: number, defaultMessage: string): string => {
  return ERROR_MESSAGES[status] || defaultMessage;
};

async function fetchWithRetry<T>(
  input: FetchInput,
  init: FetchInit = {},
  retries = 3,
  backoffMs = 1000
): Promise<T> {
  let lastError: ApiError | null = null;

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
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
        const rawMessage =
          (payload && typeof payload === 'object' && 'detail' in payload
            ? String((payload as { detail?: unknown }).detail)
            : null) || response.statusText || 'Request failed';

        const userMessage = getUserFriendlyMessage(response.status, rawMessage);
        const isRetryable = isRetryableError(response.status);

        throw new ApiError(userMessage, response.status, payload, isRetryable);
      }

      if (!isJson) {
        return undefined as T;
      }

      const data = await parseBody();
      return data as T;
    } catch (error) {
      // Handle network errors (fetch throws TypeError on network failure)
      if (error instanceof TypeError) {
        const networkError = new ApiError(
          'Network error. Please check your connection and try again.',
          0,
          null,
          true
        );
        lastError = networkError;
      } else if (error instanceof ApiError) {
        lastError = error;
      } else {
        // Unexpected error type
        throw error;
      }

      // Determine if we should retry
      const shouldRetry = lastError.isRetryable && attempt < retries;

      if (shouldRetry) {
        // Exponential backoff: 1s, 2s, 4s
        const delay = backoffMs * Math.pow(2, attempt);
        await sleep(delay);
        continue;
      }

      // No more retries or error is not retryable
      throw lastError;
    }
  }

  // Should not reach here, but TypeScript needs this
  throw lastError || new ApiError('Unknown error', 0, null);
}

export async function request<T>(input: FetchInput, init: FetchInit = {}): Promise<T> {
  return fetchWithRetry<T>(input, init);
}
