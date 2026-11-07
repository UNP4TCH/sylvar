/**
 * Stale-response guard. Call next() before starting a request; the returned function reports whether
 * that request is still the latest one. invalidate() marks every outstanding request as stale
 * (use it when the workspace/client context changes).
 */
export interface LatestGuard {
  next(): () => boolean;
  invalidate(): void;
}

export function createLatestGuard(): LatestGuard {
  let current = 0;
  return {
    next() {
      const id = ++current;
      return () => id === current;
    },
    invalidate() {
      current += 1;
    },
  };
}
