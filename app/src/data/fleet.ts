/** Agent operations fleet data for the Agents panel. Mirrors AGENTS_OPS in the prototype. */
export interface AgentOp {
  name: string
  role: string
  avatar: string
  color: string
  status: 'online' | 'busy' | 'idle'
  success: number
  today: number
  completed: number
  total: number
  model: string
  lastActive: string
}

export function agentOps(accent: string): AgentOp[] {
  return [
    { name: 'Hermes', role: 'Orchestrator', avatar: 'H', color: accent, status: 'online', success: 97, today: 14, completed: 312, total: 322, model: 'Claude Sonnet 4.6', lastActive: 'just now' },
    { name: 'rvc-runner', role: 'Realtime voice', avatar: 'R', color: '#2dd4bf', status: 'busy', success: 91, today: 6, completed: 88, total: 97, model: 'Claude Opus 4', lastActive: '2m ago' },
    { name: 'atlas-etl', role: 'ETL automation', avatar: 'A', color: '#5aa2f0', status: 'busy', success: 99, today: 9, completed: 204, total: 206, model: 'Claude Haiku 4', lastActive: 'just now' },
    { name: 'npc-builder', role: 'NPC content', avatar: 'N', color: '#9b8cff', status: 'idle', success: 88, today: 0, completed: 142, total: 161, model: 'Claude Sonnet 4.6', lastActive: '1h ago' },
    { name: 'ops-bot', role: 'Infra & ops', avatar: 'O', color: '#4ade80', status: 'idle', success: 95, today: 2, completed: 97, total: 102, model: 'Claude Haiku 4', lastActive: '18m ago' },
  ]
}

export const AG_STATUS: Record<AgentOp['status'], { label: string; color: string }> = {
  online: { label: 'Online', color: '#4ade80' },
  busy: { label: 'Running', color: '#2dd4bf' },
  idle: { label: 'Idle', color: '#6a7088' },
}

/** Fleet summary metric tiles. */
export interface FleetMetric {
  value: string
  label: string
  color: string
}

export function fleetSummary(accent: string): FleetMetric[] {
  return [
    { value: '5', label: 'Agents', color: accent },
    { value: '2', label: 'Active now', color: '#2dd4bf' },
    { value: '31', label: 'Tasks today', color: '#5aa2f0' },
    { value: '95%', label: 'Success rate', color: '#4ade80' },
    { value: '1.2s', label: 'Avg latency', color: '#9b8cff' },
  ]
}
