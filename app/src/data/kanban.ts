/** Kanban board data model + helpers. Mirrors the prototype board's state & logic. */

export type LaneId = 'triage' | 'todo' | 'ready' | 'running' | 'blocked' | 'done'

export interface Lane {
  id: LaneId
  label: string
  color: string
}

export const LANES: Lane[] = [
  { id: 'triage', label: 'Triage', color: '#9b8cff' },
  { id: 'todo', label: 'Todo', color: '#5aa2f0' },
  { id: 'ready', label: 'Ready', color: '#f6b73c' },
  { id: 'running', label: 'Running', color: '#2dd4bf' },
  { id: 'blocked', label: 'Blocked', color: '#fb6f6f' },
  { id: 'done', label: 'Done', color: '#4ade80' },
]

export const LANE_MAP: Record<LaneId, Lane> = LANES.reduce(
  (m, c) => {
    m[c.id] = c
    return m
  },
  {} as Record<LaneId, Lane>,
)

export interface Task {
  id: string
  title: string
  priority: number
  ageSec: number
  status: LaneId
  tenant: string
  assignee: string | null
  skills: string[]
  branch: string
  desc: string
  blockReason?: string
}

/** Project (tenant) metadata for the dropdown title. */
export const PROJ_META: Record<string, { label: string; dot: string }> = {
  'dm-voice-board': { label: 'DM Voice Board', dot: '#f6b73c' },
  'atlas-crm': { label: 'Atlas CRM', dot: '#5aa2f0' },
  internal: { label: 'Internal Ops', dot: '#4ade80' },
}

/** Numeric priority → color (>=7 red, >=5 amber, >=3 blue, >=1 violet). */
export function priColor(p: number): string {
  const n = Number(p) || 0
  if (n >= 7) return '#fb6f6f'
  if (n >= 5) return '#f6b73c'
  if (n >= 3) return '#5aa2f0'
  if (n >= 1) return '#9b8cff'
  return '#818799'
}

/** Staleness level mirroring the real WebUI thresholds. */
export function staleLevel(status: LaneId, sec: number): 'red' | 'amber' | null {
  const n = Number(sec)
  if (!Number.isFinite(n)) return null
  if ((status === 'running' && n > 3600) || (status === 'blocked' && n > 86400)) return 'red'
  if ((status === 'running' && n > 600) || (status === 'ready' && n > 3600) || (status === 'blocked' && n > 3600)) return 'amber'
  return null
}

export function fmtDur(sec: number): string {
  const n = Number(sec)
  if (!Number.isFinite(n) || n <= 0) return ''
  if (n < 60) return `${Math.round(n)}s`
  if (n < 3600) return `${Math.round(n / 60)}m`
  if (n < 86400) return `${Math.round(n / 3600)}h`
  return `${Math.round(n / 86400)}d`
}

export function initials(s: string | null): string {
  return (s || '').replace(/[^a-zA-Z0-9]/g, '').slice(0, 2).toUpperCase()
}
