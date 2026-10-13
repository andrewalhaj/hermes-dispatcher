/**
 * Timestamp helpers for log rendering.
 *
 * Log lines arrive raw from heterogeneous backends (kanban files prefixed
 * with "[<file>.log]", Python logging's comma-millisecond timestamps,
 * journalctl output), so any "timestamp" captured by a loose regex may not
 * be parseable by `new Date()`. `Date.prototype.toISOString` is the one
 * Date method that throws (RangeError: Invalid time value) on an Invalid
 * Date, so all display formatting must go through these guards.
 */

/** True when `raw` parses to a valid JS Date. */
export function isValidTimestamp(raw: string | undefined | null): boolean {
  if (!raw) return false
  return !isNaN(new Date(raw).getTime())
}

/**
 * Normalize a captured timestamp: return `raw` when it parses as a date,
 * otherwise fall back to the current time as ISO. Guarantees downstream
 * consumers a parseable timestamp.
 */
export function toValidTimestamp(raw: string | undefined | null): string {
  return isValidTimestamp(raw) ? (raw as string) : new Date().toISOString()
}

/**
 * Format a timestamp as ISO for display without ever throwing: invalid
 * inputs render as their raw string instead of crashing the component.
 */
export function safeIso(ts: string): string {
  const d = new Date(ts)
  return isNaN(d.getTime()) ? ts : d.toISOString()
}
