export type PanelId =
  | 'overview'
  | 'chat'
  | 'kanban'
  | 'agents'
  | 'plugins'
  | 'memory'
  | 'logs'
  | 'insights'
  | 'sessions'
  | 'profiles'
  | 'settings'
  | 'workspace'

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

// ── Chat ────────────────────────────────────────────────────────────────────

export type MessageRole = 'user' | 'agent' | 'plan'

export interface Message {
  id: string
  role: MessageRole
  text: string
  at: string
}

export interface PastSession {
  id: string
  title: string
  when: string
  msgs: { role: MessageRole; text: string; at: string }[]
}

export type PlanStepStatus = 'success' | 'active' | 'error' | 'pending'

/** A line inside a step's detail box: either a key/value row or free text. */
export interface PlanDetailLine {
  label?: string
  value?: string
  valueColor?: string
  text?: string
  color?: string
  indent?: number
}

export interface PlanStepDetail {
  boxBg: string
  boxBorder: string
  lead?: { kind: 'spinner' | 'check'; text: string; color: string }
  lines: PlanDetailLine[]
}

export interface PlanStep {
  id: string
  title: string
  status: PlanStepStatus
  duration?: string
  defaultExpanded?: boolean
  detail?: PlanStepDetail
}
