import { ReactNode, useState, useEffect, createContext, useContext } from 'react';
import toast, { Toaster, Toast as HotToast } from 'react-hot-toast';
import './Toast.css';

// ARIA Live Announcer for screen readers
type AnnouncerContextType = {
  announce: (message: string) => void;
};

const AnnouncerContext = createContext<AnnouncerContextType | null>(null);

function AriaLiveAnnouncer({ children }: { children: ReactNode }) {
  const [announcements, setAnnouncements] = useState<string[]>([]);

  const announce = (message: string) => {
    setAnnouncements(prev => [...prev, message]);

    // Clear announcement after it's been read
    setTimeout(() => {
      setAnnouncements(prev => prev.slice(1));
    }, 1000);
  };

  return (
    <AnnouncerContext.Provider value={{ announce }}>
      {children}
      {/* ARIA live region for screen reader announcements */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {announcements[0] || ''}
      </div>
    </AnnouncerContext.Provider>
  );
}

function useAnnouncer() {
  const context = useContext(AnnouncerContext);
  if (!context) {
    throw new Error('useAnnouncer must be used within AriaLiveAnnouncer');
  }
  return context;
}

// Toast provider component
export function ToastProvider({ children }: { children: ReactNode }) {
  const isBrowser = typeof window !== 'undefined';

  return (
    <AriaLiveAnnouncer>
      {children}
      {isBrowser ? (
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: {
              background: 'var(--bg-elevated)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border-primary)',
              borderRadius: 'var(--radius-lg)',
              padding: 'var(--space-4)',
              boxShadow: 'var(--shadow-lg)',
              maxWidth: '500px',
            },
            success: {
              iconTheme: {
                primary: 'var(--green-600)',
                secondary: 'white',
              },
              style: {
                borderLeft: '4px solid var(--green-600)',
              },
            },
            error: {
              iconTheme: {
                primary: 'var(--red-600)',
                secondary: 'white',
              },
              style: {
                borderLeft: '4px solid var(--red-600)',
              },
              duration: 6000,
            },
            loading: {
              iconTheme: {
                primary: 'var(--blue-600)',
                secondary: 'white',
              },
              style: {
                borderLeft: '4px solid var(--blue-600)',
              },
            },
          }}
        />
      ) : null}
    </AriaLiveAnnouncer>
  );
}

// Accessible toast helper functions
type ToastType = 'success' | 'error' | 'loading' | 'custom';

function createAccessibleToast(type: ToastType) {
  return (message: string, options?: { duration?: number }) => {
    // Guard against SSR/test environments
    if (typeof window === 'undefined') {
      return '';
    }

    let toastId: string;

    switch (type) {
      case 'success':
        toastId = toast.success(message, options);
        break;
      case 'error':
        toastId = toast.error(message, options);
        break;
      case 'loading':
        toastId = toast.loading(message, options);
        break;
      default:
        toastId = toast(message, options);
    }

    // Announce to screen readers
    // Note: We'll use a custom event to communicate with the announcer
    window.dispatchEvent(
      new CustomEvent('toast-announce', { detail: { message } })
    );

    return toastId;
  };
}

// Hook to connect toast announcements to ARIA live region
export function useToastAnnouncer() {
  const { announce } = useAnnouncer();

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const handleAnnouncement = (event: Event) => {
      const customEvent = event as CustomEvent<{ message: string }>;
      announce(customEvent.detail.message);
    };

    window.addEventListener('toast-announce', handleAnnouncement);
    return () => {
      window.removeEventListener('toast-announce', handleAnnouncement);
    };
  }, [announce]);
}

// Export accessible toast functions
export const accessibleToast = {
  success: createAccessibleToast('success'),
  error: createAccessibleToast('error'),
  loading: createAccessibleToast('loading'),
  custom: createAccessibleToast('custom'),
  dismiss: (toastId?: string) => toast.dismiss(toastId),
  promise: <T,>(
    promise: Promise<T>,
    messages: {
      loading: string;
      success: string | ((data: T) => string);
      error: string | ((err: unknown) => string);
    }
  ) => {
    if (typeof window === 'undefined') {
      return promise;
    }

    return toast.promise(promise, messages);
  },
};

// Re-export toast types for convenience
export type { HotToast as Toast };
