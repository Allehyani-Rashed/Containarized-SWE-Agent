import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { getPatStatus, initialPatStatus } from '../api/integrations';
import { PatStatus } from '../types';

const PatStatusContext = createContext<
  | {
      status: PatStatus;
      isLoading: boolean;
      error: string | null;
      lastRefreshedAt: string | null;
      refresh: () => Promise<void>;
      updateStatus: (status: PatStatus) => void;
      clearError: () => void;
    }
  | undefined
>(undefined);

type ProviderProps = {
  children: ReactNode;
};

export function PatStatusProvider({ children }: ProviderProps) {
  const [status, setStatus] = useState<PatStatus>(initialPatStatus);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const requestIdRef = useRef(0);
  const isMountedRef = useRef(true);
  const hasLoadedRef = useRef(false);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const applyStatus = useCallback((next: PatStatus) => {
    setStatus(next);
    setError(null);
    setLastRefreshedAt(new Date().toISOString());
    hasLoadedRef.current = true;
  }, []);

  const refresh = useCallback(async () => {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    if (!hasLoadedRef.current) {
      setIsLoading(true);
    }
    try {
      const snapshot = await getPatStatus();
      if (!isMountedRef.current || requestIdRef.current !== requestId) {
        return;
      }
      applyStatus(snapshot);
    } catch (apiError) {
      if (!isMountedRef.current || requestIdRef.current !== requestId) {
        return;
      }
      const message =
        apiError instanceof Error ? apiError.message : 'Failed to load credential status';
      setError(message);
    } finally {
      if (isMountedRef.current && requestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  }, [applyStatus]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void refresh();
    }, 15000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const value = useMemo(
    () => ({
      status,
      isLoading,
      error,
      lastRefreshedAt,
      refresh,
      updateStatus: applyStatus,
      clearError: () => setError(null),
    }),
    [status, isLoading, error, lastRefreshedAt, refresh, applyStatus],
  );

  return <PatStatusContext.Provider value={value}>{children}</PatStatusContext.Provider>;
}

export function usePatStatus() {
  const context = useContext(PatStatusContext);
  if (!context) {
    throw new Error('usePatStatus must be used within a PatStatusProvider');
  }
  return context;
}
