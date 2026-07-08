const OVERRIDES: Record<string, string> = {
  'ha-bot': 'HA Bot',
}

/** Convert a raw profile/agent key (e.g. "coder-c", "swarm-worker-a") to a
 *  human-readable display name ("Coder C", "Swarm Worker A"). */
export function profileDisplayName(key: string | null | undefined): string {
  if (!key) return 'Default'
  if (OVERRIDES[key]) return OVERRIDES[key]
  return key.split('-').map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')
}
