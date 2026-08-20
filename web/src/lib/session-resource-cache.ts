type CacheEntry<T> = {
  hasValue: boolean;
  value?: T;
  expiresAt: number;
  pending?: Promise<T>;
};

export interface SessionResourceOptions {
  ttlMs: number;
  force?: boolean;
}

const entries = new Map<string, CacheEntry<unknown>>();

/**
 * Returns the last successful value, including stale data. Pages use this to
 * render immediately while an expired resource refreshes in the background.
 */
export function readSessionResource<T>(key: string): T | undefined {
  const entry = entries.get(key) as CacheEntry<T> | undefined;
  return entry?.hasValue ? entry.value : undefined;
}

/** Stores a value produced by a mutation so a later route mount sees it. */
export function writeSessionResource<T>(key: string, value: T, ttlMs: number): void {
  entries.set(key, {
    hasValue: true,
    value,
    expiresAt: Date.now() + ttlMs,
  });
}

/**
 * Loads one session resource with TTL and in-flight request deduplication.
 * A failed refresh keeps the last successful value available for rendering.
 */
export function loadSessionResource<T>(
  key: string,
  loader: () => Promise<T>,
  { ttlMs, force = false }: SessionResourceOptions,
): Promise<T> {
  const current = entries.get(key) as CacheEntry<T> | undefined;
  const fresh = Boolean(current?.hasValue && current.expiresAt > Date.now());

  if (!force && fresh) return Promise.resolve(current?.value as T);
  if (!force && current?.pending) return current.pending;

  const pending = Promise.resolve()
    .then(loader)
    .then(
      (value) => {
        const latest = entries.get(key) as CacheEntry<T> | undefined;
        // A forced request may have superseded this one. Only the newest request
        // is allowed to replace the shared value.
        if (latest?.pending === pending) {
          writeSessionResource(key, value, ttlMs);
        }
        return value;
      },
      (error: unknown) => {
        const latest = entries.get(key) as CacheEntry<T> | undefined;
        if (latest?.pending === pending) {
          if (latest.hasValue) {
            entries.set(key, {
              hasValue: true,
              value: latest.value,
              expiresAt: latest.expiresAt,
            });
          } else {
            entries.delete(key);
          }
        }
        throw error;
      },
    );

  entries.set(key, {
    hasValue: current?.hasValue ?? false,
    value: current?.value,
    expiresAt: current?.expiresAt ?? 0,
    pending,
  });
  return pending;
}

/** Marks a retained value stale without making the next screen flash empty. */
export function expireSessionResource(key: string): void {
  const current = entries.get(key);
  if (!current) return;
  entries.set(key, { ...current, expiresAt: 0 });
}

export function clearSessionResourceCache(): void {
  entries.clear();
}
