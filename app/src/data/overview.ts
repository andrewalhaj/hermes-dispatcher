import { ACCENT } from './agents'

export interface StatTileData {
  value: string
  label: string
  accent: string
  glowX: string
  glowY: string
  sub: string
  target: string
  iconPath: string
}

export interface RingSeg {
  color: string
  dash: string
  offset: string
}

export interface BreakdownRow {
  key: string
  name: string
  color: string
  count: number
  pct: number
}

export interface HeatCell {
  bg: string
  delay: string
}

export interface HeatRow {
  key: string
  name: string
  icon: string
  color: string
  cells: HeatCell[]
}

export interface OverviewData {
  eyebrow: string
  greeting: string
  date: string
  chips: { label: string; dot: string }[]
  kpis: { val: string; lbl: string }[]
  stats: StatTileData[]
  ringSegs: RingSeg[]
  ringTotal: string
  breakdown: BreakdownRow[]
  heatRows: HeatRow[]
}

const AGENTS = [
  { key: 'rvc-runner', name: 'rvc-runner', icon: '◆', color: '#2dd4bf', count: 48 },
  { key: 'atlas-etl', name: 'atlas-etl', icon: '▣', color: '#5aa2f0', count: 37 },
  { key: 'npc-builder', name: 'npc-builder', icon: '❖', color: '#9b8cff', count: 26 },
  { key: 'ops-bot', name: 'ops-bot', icon: '⬢', color: ACCENT, count: 14 },
  { key: 'w-okada-01', name: 'w-okada-01', icon: '▲', color: '#4ade80', count: 6 },
]

const fmt = (n: number) => (n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n))

/** Build the deterministic Overview view-model (mirrors the prototype's buildOverview). */
export function buildOverview(accent = ACCENT): OverviewData {
  const total = AGENTS.reduce((a, x) => a + x.count, 0)

  // Segmented radial gauge.
  const R = 100
  const C = 2 * Math.PI * R
  const GAP = 6
  let cum = 0
  const ringSegs: RingSeg[] = AGENTS.map((a) => {
    const frac = a.count / total
    const len = Math.max(0, frac * C - GAP)
    const seg = { color: a.color, dash: `${len.toFixed(1)} ${(C - len).toFixed(1)}`, offset: (-cum * C).toFixed(1) }
    cum += frac
    return seg
  })

  const breakdown: BreakdownRow[] = AGENTS.map((a) => ({
    key: a.key,
    name: a.name,
    color: a.color,
    count: a.count,
    pct: Math.round((a.count / total) * 100),
  }))

  // 24h activity heatmap, deterministic.
  const alpha = [6, 26, 48, 72, 100]
  const heatRows: HeatRow[] = AGENTS.map((a, ai) => {
    const cells: HeatCell[] = []
    for (let h = 0; h < 24; h++) {
      const v = 2 + 2 * Math.sin((h / 24) * Math.PI * 2 + ai * 1.3) + Math.cos((h + ai * 5) * 0.7)
      let lvl = Math.max(0, Math.min(4, Math.round((v / 4) * 4)))
      if (h < 6) lvl = Math.max(0, lvl - 2)
      cells.push({
        bg: lvl === 0 ? 'rgba(255,255,255,0.04)' : `color-mix(in oklab, ${a.color} ${alpha[lvl]}%, transparent)`,
        delay: `${(h * 0.014).toFixed(3)}s`,
      })
    }
    return { key: a.key, name: a.name, icon: a.icon, color: a.color, cells }
  })

  const now = new Date()
  const hr = now.getHours()
  const part = hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening'
  const date = now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
  const running = 2

  return {
    eyebrow: 'Mission Overview',
    greeting: `${part}, operator`,
    date,
    chips: [
      { label: 'Dispatcher live', dot: '#4ade80' },
      { label: `${running} running`, dot: '#2dd4bf' },
      { label: '3 ready', dot: accent },
      { label: '2 blocked', dot: '#fb6f6f' },
    ],
    kpis: [
      { val: fmt(total), lbl: 'Tasks Run' },
      { val: String(running), lbl: 'Active Sessions' },
      { val: '7', lbl: 'Day Streak' },
    ],
    stats: [
      { value: fmt(total), label: 'Tasks Run', accent, glowX: '30%', glowY: '74%', sub: 'View the board', target: 'kanban', iconPath: 'M9 11l3 3L20 5M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11' },
      { value: String(running), label: 'Active Sessions', accent: '#2dd4bf', glowX: '72%', glowY: '18%', sub: 'Open chat', target: 'chat', iconPath: 'M3 12h4l3 8 4-16 3 8h4' },
      { value: '3', label: 'Tenants', accent: '#5aa2f0', glowX: '18%', glowY: '34%', sub: 'View logs', target: 'logs', iconPath: 'M3 21V8l9-5 9 5v13M9 21v-6h6v6' },
      { value: '5.0k', label: 'Memory Items', accent: '#9b8cff', glowX: '84%', glowY: '64%', sub: 'Open Memory Galaxy', target: 'memory', iconPath: 'M9 3a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z' },
    ],
    ringSegs,
    ringTotal: fmt(total),
    breakdown,
    heatRows,
  }
}
