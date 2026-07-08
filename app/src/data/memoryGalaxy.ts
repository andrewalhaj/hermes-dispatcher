import type { GalaxyData, MemNode, MemTier } from './phase3'

interface ApiNode {
  id: string
  label: string
  tier: string
  body: string
}

interface ApiGalaxyResponse {
  nodes: ApiNode[]
  edges: unknown[]
}

// Keys must match the `tier` strings emitted by routes/memory.py:get_galaxy().
// Memory files: hot (MEMORY.md), warm (USER.md), soul, agents.
// References dir: cold. Honcho peer-card: honcho.
// Knowledge store rows are split by tag into four sub-tiers via _kb_tier():
// user-profile, session, offload, knowledge — each needs a distinct label here,
// otherwise unmapped keys fall back to `cold` and all render as "References".
const TIER_META: Record<string, { color: string; label: string; center: [number, number, number] }> = {
  hot:  { color: '#f6b73c', label: 'Memory',       center: [-2.5,  0.6,  0.5] },
  warm: { color: '#5aa2f0', label: 'User Profile',  center: [ 2.4,  0.9, -0.8] },
  cold: { color: '#6a7088', label: 'References',    center: [ 0.2,  2.3,  0.9] },
  soul:   { color: '#a78bfa', label: 'Soul',       center: [-1.0, -1.8,  0.8] },
  agents: { color: '#34d399', label: 'Agents',      center: [ 1.2, -1.6, -1.0] },
  honcho: { color: '#f472b6', label: 'Honcho',      center: [ 0.0,  0.0,  2.2] },
  knowledge: { color: '#fb923c', label: 'Knowledge', center: [-0.8, 1.2, -1.8] },
  'user-profile': { color: '#22d3ee', label: 'Profile Facts', center: [ 1.8, -0.4,  1.6] },
  session:        { color: '#e879f9', label: 'Sessions',      center: [-1.9,  1.4, -0.6] },
  offload:        { color: '#a3e635', label: 'Offload',       center: [ 0.6, -2.1, -1.4] },
}

export async function fetchGalaxyData(): Promise<GalaxyData> {
  const res = await fetch('/api/memory/galaxy')
  if (!res.ok) throw new Error('Failed to fetch galaxy data')
  const data: ApiGalaxyResponse = await res.json()
  return transformGalaxy(data)
}

export function transformGalaxy(data: ApiGalaxyResponse): GalaxyData {
  if (!data.nodes || data.nodes.length === 0) {
    return { nodes: [], links: [], tiers: [] }
  }

  // Deterministic pseudo-random — same as buildGalaxy()
  let seed = 20240617
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff
    return seed / 0x7fffffff
  }
  const gas = () => (rnd() + rnd() + rnd() - 1.5) * 0.95

  const nodes: MemNode[] = data.nodes.map((n) => {
    const meta = TIER_META[n.tier] ?? TIER_META.cold
    const imp = 0.5 + rnd() * 0.45
    const sp = 1.55 - imp * 0.5
    return {
      id: n.id,
      tier: n.tier,
      tierLabel: meta.label,
      color: meta.color,
      title: n.label,
      importance: imp,
      ageDays: Math.round(2 + rnd() * 180),
      recall: Math.max(35, Math.round(imp * 100 - rnd() * 14)),
      x: meta.center[0] * 0.6 + gas() * sp,
      y: meta.center[1] * 0.6 + gas() * sp,
      z: meta.center[2] * 0.6 + gas() * sp,
    }
  })

  // Nearest-3 links — same algorithm as buildGalaxy()
  const links: [number, number][] = []
  const seen = new Set<string>()
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i]
    const ds: [number, number][] = []
    for (let j = 0; j < nodes.length; j++) {
      if (j === i) continue
      const b = nodes[j]
      ds.push([(a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2, j])
    }
    ds.sort((p, q) => p[0] - q[0])
    for (let k = 0; k < Math.min(3, ds.length); k++) {
      const j = ds[k][1]
      const key = i < j ? `${i}-${j}` : `${j}-${i}`
      if (!seen.has(key)) {
        seen.add(key)
        links.push([i, j])
      }
    }
  }

  // Label the most-important node per tier
  const bestByTier: Record<string, number> = {}
  nodes.forEach((m, idx) => {
    if (bestByTier[m.tier] === undefined || nodes[bestByTier[m.tier]].importance < m.importance) {
      bestByTier[m.tier] = idx
    }
  })
  Object.values(bestByTier).forEach((idx) => { nodes[idx].label = true })

  // Tier summary
  const tierCount: Record<string, number> = {}
  nodes.forEach((n) => { tierCount[n.tier] = (tierCount[n.tier] ?? 0) + 1 })
  const tiers: MemTier[] = Object.entries(tierCount).map(([tierId, count]) => {
    const meta = TIER_META[tierId] ?? TIER_META.cold
    return { id: tierId, label: meta.label, color: meta.color, count }
  })

  return { nodes, links, tiers }
}
