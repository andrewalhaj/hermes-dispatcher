/** Shared localStorage helpers — safe wrappers for environments where
 * storage may be unavailable (private browsing, sandboxed iframes, etc.).
 */

export function lsGet(key: string, fallback: string): string {
  try { return localStorage.getItem(key) ?? fallback } catch { return fallback }
}

export function lsGetJson<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key)
    return v ? (JSON.parse(v) as T) : fallback
  } catch { return fallback }
}

export function lsSet(key: string, value: string): void {
  try { localStorage.setItem(key, value) } catch { /* storage unavailable */ }
}
