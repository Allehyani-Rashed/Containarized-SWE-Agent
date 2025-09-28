import { RefObject, useEffect } from 'react';

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea, input, select, details,[tabindex]:not([tabindex="-1"])';

export function useFocusTrap(
  containerRef: RefObject<HTMLElement | null>,
  enabled: boolean,
  initialFocusRef?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!enabled) {
      return;
    }
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const focusable = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const target = initialFocusRef?.current ?? first ?? null;

    if (target) {
      target.focus();
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') {
        return;
      }
      if (!focusable.length) {
        event.preventDefault();
        return;
      }

      const active = document.activeElement as HTMLElement | null;
      const focusFirst = first ?? focusable[0];
      const focusLast = last ?? focusable[focusable.length - 1];

      if (event.shiftKey) {
        if (!active || !container.contains(active) || active === focusFirst) {
          event.preventDefault();
          focusLast?.focus();
        }
      } else if (active === focusLast) {
        event.preventDefault();
        focusFirst?.focus();
      }
    };

    container.addEventListener('keydown', handleKeyDown);

    return () => {
      container.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus?.();
    };
  }, [containerRef, enabled, initialFocusRef]);
}
