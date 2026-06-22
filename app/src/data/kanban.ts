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
}

/** Project (tenant) metadata for the dropdown title. */
export const PROJ_META: Record<string, { label: string; dot: string }> = {
  'dm-voice-board': { label: 'DM Voice Board', dot: '#f6b73c' },
  'atlas-crm': { label: 'Atlas CRM', dot: '#5aa2f0' },
  internal: { label: 'Internal Ops', dot: '#4ade80' },
}

const ageMin = (m: number) => m * 60

/** Deterministic seed board — all mock data. */
export function seedTasks(): Task[] {
  return [
    { id: 't1', title: 'POC: w-okada install + 3070 latency gate', priority: 8, ageSec: 7200, status: 'ready', tenant: 'dm-voice-board', assignee: null, skills: ['voice-rt'], branch: 'poc/latency-gate', desc: "GO/NO-GO gate. Install w-okada one-click on the DM's Windows 3070 laptop, latency-test one stock RVC model (speak → hear), set output = room speaker + mic = headset, confirm no feedback. Prove latency BEFORE building any NPC content." },
    { id: 't2', title: 'First hero NPC: end-to-end proof', priority: 6, ageSec: 12000, status: 'blocked', tenant: 'dm-voice-board', assignee: null, skills: ['voice-rt', 'content'], branch: '', desc: 'Single NPC, full loop: reference audio → trained voice → live conversion in session. Gated on the latency POC passing.' },
    { id: 't3', title: 'Build the board: hero voices + runtime tuning', priority: 5, ageSec: 95000, status: 'blocked', tenant: 'dm-voice-board', assignee: null, skills: ['content'], branch: '', desc: 'Stand up the full voice board with all hero voices and per-voice runtime tuning. Gated on the hero NPC proof.' },
    { id: 't4', title: 'Design spec: real-time RVC pipeline', priority: 7, ageSec: 25200, status: 'done', tenant: 'dm-voice-board', assignee: 'coder-d', skills: ['content'], branch: '', desc: 'Full design doc covering capture, training, routing, and the latency gate.' },
    { id: 't5', title: 'Triage incoming latency reports', priority: 4, ageSec: 5400, status: 'triage', tenant: 'dm-voice-board', assignee: null, skills: [], branch: '', desc: 'Sort and label new latency reports from playtesters.' },
    { id: 't6', title: 'Capture clean reference audio (3 voices)', priority: 5, ageSec: 9000, status: 'todo', tenant: 'dm-voice-board', assignee: null, skills: ['content'], branch: '', desc: 'Record 3 NPC reference voices, treated room, 48kHz, ~5 min each.' },
    { id: 't7', title: 'Mic routing: VB-Cable + headset isolation', priority: 6, ageSec: 4800, status: 'ready', tenant: 'dm-voice-board', assignee: null, skills: ['voice-rt'], branch: 'audio/routing', desc: 'Route headset mic in, room speaker out, no feedback loop. Verify with the latency rig.' },
    { id: 't8', title: 'Benchmark RVC models on the 3070', priority: 6, ageSec: 2400, status: 'running', tenant: 'dm-voice-board', assignee: 'executor', skills: ['gpu-bench'], branch: 'bench/rvc-3070', desc: 'Measure conversion latency + GPU headroom across 4 candidate RVC models.' },
    { id: 't9', title: 'Contact dedupe job', priority: 3, ageSec: 30000, status: 'done', tenant: 'atlas-crm', assignee: 'coder-c', skills: ['etl'], branch: '', desc: 'Fuzzy-match and merge duplicate contacts across imported lists.' },
    { id: 't10', title: 'Nightly export to S3', priority: 4, ageSec: 1200, status: 'running', tenant: 'atlas-crm', assignee: 'coder-c', skills: ['etl'], branch: 'etl/nightly-s3', desc: 'Snapshot the CRM nightly and ship to the S3 cold bucket.' },
    { id: 't11', title: 'Webhook retry backoff', priority: 5, ageSec: 9600, status: 'todo', tenant: 'atlas-crm', assignee: null, skills: ['etl'], branch: '', desc: 'Add exponential backoff + dead-letter queue for failed outbound webhooks.' },
    { id: 't12', title: 'Rotate API keys', priority: 7, ageSec: 4200, status: 'ready', tenant: 'internal', assignee: null, skills: ['infra'], branch: 'sec/key-rotation', desc: 'Rotate all service API keys and update the secret store. Quarterly cadence.' },
    { id: 't13', title: 'Upgrade worker pool to py3.12', priority: 4, ageSec: 36000, status: 'done', tenant: 'internal', assignee: 'coder-e', skills: ['infra'], branch: '', desc: 'Roll all workers to Python 3.12, verify deps, redeploy.' },
    { id: 't14', title: 'Dashboard: dispatcher metrics', priority: 3, ageSec: 4800, status: 'triage', tenant: 'internal', assignee: null, skills: [], branch: '', desc: 'Build a live view of dispatch throughput, queue depth, and worker utilization.' },
    { id: 't15', title: 'Write NPC dialogue trees', priority: 2, ageSec: 6600, status: 'todo', tenant: 'dm-voice-board', assignee: null, skills: ['content'], branch: '', desc: 'Branching dialogue for the three hero NPCs.' },
    { id: 't16', title: 'Playtest session #1 notes', priority: 3, ageSec: 21600, status: 'done', tenant: 'dm-voice-board', assignee: 'coder-d', skills: [], branch: '', desc: 'Write up findings from the first live playtest.' },
    { id: 't17', title: 'Fix timezone bug in reports', priority: 6, ageSec: 10200, status: 'blocked', tenant: 'atlas-crm', assignee: null, skills: ['etl'], branch: '', desc: 'Reports render in UTC instead of the tenant timezone. Blocked pending product decision on default tz.' },
    { id: 't18', title: 'Incident postmortem doc', priority: 5, ageSec: 54000, status: 'done', tenant: 'internal', assignee: 'coder-e', skills: [], branch: '', desc: 'Postmortem for the dispatcher queue backup on the 9th.' },
  ]
}

export interface Worker {
  id: string
  name: string
  skill: string
  status: 'idle' | 'busy'
  taskId: string | null
}

export function seedWorkers(): Worker[] {
  return [
    { id: 'swarm-worker-b', name: 'swarm-worker-b', skill: 'voice-rt', status: 'idle', taskId: null },
    { id: 'executor', name: 'executor', skill: 'gpu-bench', status: 'busy', taskId: 't8' },
    { id: 'coder-c', name: 'coder-c', skill: 'etl', status: 'busy', taskId: 't10' },
    { id: 'coder-d', name: 'coder-d', skill: 'content', status: 'idle', taskId: null },
    { id: 'coder-e', name: 'coder-e', skill: 'infra', status: 'idle', taskId: null },
  ]
}

void ageMin

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
