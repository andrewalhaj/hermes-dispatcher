// Display-name overrides for profile/agent keys whose auto-title-cased form
// would read wrong. Empty now that `ha-bot` (deleted 2026-06-25) is gone; the
// generic title-caser below handles every live profile (coder-c → "Coder C").
const OVERRIDES: Record<string, string> = {}

/** Convert a raw profile/agent key (e.g. "coder-c", "swarm-worker-a") to a
 *  human-readable display name ("Coder C", "Swarm Worker A"). */
export function profileDisplayName(key: string | null | undefined): string {
  if (!key) return 'Default'
  if (OVERRIDES[key]) return OVERRIDES[key]
  return key.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}
