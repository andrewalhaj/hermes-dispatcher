export type PanelId =
  | 'overview'
  | 'chat'
  | 'kanban'
  | 'agents'
  | 'plugins'
  | 'memory'
  | 'logs'
  | 'insights'
  | 'profiles'
  | 'settings'

export type AgentStatus = 'online' | 'idle'

export interface ChatAgent {
  key: string
  name: string
  role: string
  platform: string
  icon: string
  color: string
  status: AgentStatus
  running?: boolean
}

/** Resolved live-status badge for the rail agent list. */
export interface AgentRow {
  key: string
  name: string
  dot: string
  dotGlow: string
  badge: 'LIVE' | 'RUN' | 'IDLE'
  badgeColor: string
  badgeBg: string
}
