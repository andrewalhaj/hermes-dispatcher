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

export interface BuildOverviewOpts {
  sparklineCounts?: number[]
  activeAgents?: number
  running?: number
  ready?: number
  blocked?: number
  agentBreakdown?: { name: string; count: number }[]
  agentActivity?: { name: string; hours: number[] }[]
  totalTasks?: number
}

export const PALETTE = ['#2dd4bf', '#5aa2f0', '#9b8cff', '#4ade80', '#f0a85a', '#f06a9b']

const fmt = (n: number) => (n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n))

/** Build the Overview view-model from live API data. */
export function buildOverview(accent = ACCENT, opts?: BuildOverviewOpts): OverviewData {
  const totalTasks = opts?.totalTasks ?? 0
  const agentBreakdown = opts?.agentBreakdown ?? []
  const agentActivity = opts?.agentActivity ?? []

  const running = opts?.running ?? 0
  const readyCount = opts?.ready ?? 0
  const blockedCount = opts?.blocked ?? 0
  const activeAgents = opts?.activeAgents ?? 0

  const R = 100
  const C = 2 * Math.PI * R
  const GAP = 6
  let cum = 0
  const ringSegs: RingSeg[] = agentBreakdown.map((a, i) => {
    const color = PALETTE[i] ?? '#888'
    const frac = totalTasks > 0 ? a.count / totalTasks : 0
    const len = Math.max(0, frac * C - GAP)
    const seg = { color, dash: `${len.toFixed(1)} ${(C - len).toFixed(1)}`, offset: (-cum * C).toFixed(1) }
    cum += frac
    return seg
  })

  const breakdown: BreakdownRow[] = agentBreakdown.map((a, i) => ({
    key: a.name,
    name: a.name,
    color: PALETTE[i] ?? '#888',
    count: a.count,
    pct: totalTasks > 0 ? Math.round((a.count / totalTasks) * 100) : 0,
  }))

  const alpha = [6, 26, 48, 72, 100]
  const heatRows: HeatRow[] = agentActivity.map((a, ai) => {
    const color = PALETTE[ai] ?? '#888'
    const maxCount = Math.max(1, ...a.hours)
    const cells: HeatCell[] = a.hours.map((cnt, h) => {
      const lvl = Math.max(0, Math.min(4, Math.round((cnt / maxCount) * 4)))
      return {
        bg: lvl === 0 ? 'rgba(255,255,255,0.04)' : `color-mix(in oklab, ${color} ${alpha[lvl]}%, transparent)`,
        delay: `${(h * 0.014).toFixed(3)}s`,
      }
    })
    return { key: a.name, name: a.name, icon: '●', color, cells }
  })

  const now = new Date()
  const hr = now.getHours()
  const part = hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening'
  const date = now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })

  return {
    eyebrow: 'Mission Overview',
    greeting: `${part}, operator`,
    date,
    chips: [
      { label: 'Dispatcher live', dot: '#4ade80' },
      { label: `${running} running`, dot: '#2dd4bf' },
      { label: `${readyCount} ready`, dot: accent },
      { label: `${blockedCount} blocked`, dot: '#fb6f6f' },
    ],
    kpis: [
      { val: fmt(totalTasks), lbl: 'Tasks Run' },
      { val: String(activeAgents), lbl: 'Active Sessions' },
    ],
    stats: [
      { value: fmt(totalTasks), label: 'Tasks Run', accent, glowX: '30%', glowY: '74%', sub: 'View the board', target: 'kanban', iconPath: 'M9 11l3 3L20 5M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11' },
      { value: String(activeAgents), label: 'Active Sessions', accent: '#2dd4bf', glowX: '72%', glowY: '18%', sub: 'Open chat', target: 'chat', iconPath: 'M3 12h4l3 8 4-16 3 8h4' },
    ],
    ringSegs,
    ringTotal: fmt(totalTasks),
    breakdown,
    heatRows,
  }
}
