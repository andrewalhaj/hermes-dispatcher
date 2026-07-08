import { ACCENT } from './agents'
import type { InfoObject } from './info'

// ---------------------------------------------------------------------------
// Agents panel — fleet metrics + operational agent cards
// ---------------------------------------------------------------------------

export interface FleetMetric {
  value: string
  label: string
  color: string
  window: string
  blurb: string
}

export interface AgentOp {
  name: string
  role: string
  avatar: string
  color: string
  status: 'online' | 'busy' | 'idle'
  statusLabel: string
  statusColor: string
  success: number
  today: number
  completed: number
  total: number
  model: string
  lastActive: string
}

const AG_STATUS: Record<AgentOp['status'], { l: string; c: string }> = {
  online: { l: 'Online', c: '#4ade80' },
  busy: { l: 'Running', c: '#2dd4bf' },
  idle: { l: 'Idle', c: '#6a7088' },
}

const AGENTS_OPS_RAW = [
  { name: 'Hermes', role: 'Orchestrator', avatar: 'H', color: ACCENT, status: 'online' as const, success: 97, today: 14, completed: 312, total: 322, model: 'Claude Sonnet 4.6', lastActive: 'just now' },
  { name: 'executor', role: 'Realtime voice', avatar: 'R', color: '#2dd4bf', status: 'busy' as const, success: 91, today: 6, completed: 88, total: 97, model: 'Claude Opus 4', lastActive: '2m ago' },
  { name: 'coder-c', role: 'ETL automation', avatar: 'A', color: '#5aa2f0', status: 'busy' as const, success: 99, today: 9, completed: 204, total: 206, model: 'Claude Haiku 4', lastActive: 'just now' },
  { name: 'coder-d', role: 'NPC content', avatar: 'N', color: '#9b8cff', status: 'idle' as const, success: 88, today: 0, completed: 142, total: 161, model: 'Claude Sonnet 4.6', lastActive: '1h ago' },
  { name: 'coder-e', role: 'Infra & ops', avatar: 'O', color: '#4ade80', status: 'idle' as const, success: 95, today: 2, completed: 97, total: 102, model: 'Claude Haiku 4', lastActive: '18m ago' },
]

const FLEET_BLURB: Record<string, string> = {
  Agents: 'Total worker agents registered with the dispatcher across all tenants.',
  'Active now': 'Agents currently executing a task this moment — the live concurrency of the pool.',
  'Tasks today': 'Tasks the fleet has completed since midnight in the operator timezone.',
  'Success rate': 'Share of completed tasks that finished without error over the trailing window.',
  'Avg latency': 'Mean end-to-end task turnaround across the fleet for the trailing window.',
}

export interface AgentOpView extends AgentOp {
  successPct: string
  ringDash: string
  progW: string
  avBg: string
  avBorder: string
  glowBg: string
  info: InfoObject
}

export function buildAgents(accent = ACCENT) {
  const fleet: FleetMetric[] = [
    { value: '5', label: 'Agents', color: accent, window: 'today', blurb: FLEET_BLURB.Agents },
    { value: '2', label: 'Active now', color: '#2dd4bf', window: 'now', blurb: FLEET_BLURB['Active now'] },
    { value: '31', label: 'Tasks today', color: '#5aa2f0', window: 'today', blurb: FLEET_BLURB['Tasks today'] },
    { value: '95%', label: 'Success rate', color: '#4ade80', window: '7d', blurb: FLEET_BLURB['Success rate'] },
    { value: '1.2s', label: 'Avg latency', color: '#9b8cff', window: '7d', blurb: FLEET_BLURB['Avg latency'] },
  ]
  const fleetInfo = (m: FleetMetric): InfoObject => ({
    category: 'Fleet metric',
    title: m.label,
    value: m.value,
    accent: m.color,
    desc: m.blurb,
    stats: [
      { label: 'Value', value: m.value },
      { label: 'Window', value: m.window },
    ],
  })

  const agents: AgentOpView[] = AGENTS_OPS_RAW.map((a) => {
    const st = AG_STATUS[a.status]
    return {
      ...a,
      statusLabel: st.l,
      statusColor: st.c,
      successPct: a.success + '%',
      ringDash: a.success + ' ' + (100 - a.success),
      progW: Math.min(100, a.today * 12 + 4) + '%',
      avBg: `color-mix(in oklab, ${a.color} 16%, transparent)`,
      avBorder: `color-mix(in oklab, ${a.color} 40%, transparent)`,
      glowBg: `color-mix(in oklab, ${a.color} 22%, transparent)`,
      info: {
        category: 'Agent · ' + st.l,
        title: a.name,
        accent: a.color,
        desc: `${a.role} — ${a.completed} of ${a.total} assigned tasks complete, ${a.success}% success rate.`,
        stats: [
          { label: 'Status', value: st.l },
          { label: 'Success rate', value: a.success + '%' },
          { label: 'Tasks today', value: String(a.today) },
          { label: 'Completed', value: a.completed + ' / ' + a.total },
          { label: 'Model', value: a.model },
          { label: 'Last active', value: a.lastActive },
        ],
        actionLabel: 'Open chat with ' + a.name,
      },
    }
  })

  return { fleet, fleetInfo, agents }
}

// ---------------------------------------------------------------------------
// Insights panel — KPIs, activity-by-day, tokens, models, skills
// ---------------------------------------------------------------------------

export interface InsightsData {
  period: string
  kpis: { label: string; value: string; accent: string; info: InfoObject }[]
  days: { h: string; bg: string }[]
  peak: string
  tokInPct: string
  tokOutPct: string
  tokIn: string
  tokOut: string
  tokTotal: string
  models: { name: string; sessions: string; tokens: string; cost: string; share: string; color: string }[]
  skills: { skill: string; uses: string; share: string; w: string }[]
  activityInfo: InfoObject
  tokenInfo: InfoObject
  modelsInfo: InfoObject
  skillsInfo: InfoObject
}

const KPI_BLURB: Record<string, string> = {
  Sessions: 'Total chat & task sessions started in the period across every agent and tenant.',
  Messages: 'User and agent messages exchanged in the period — a proxy for interaction volume.',
  Tokens: 'Combined input + output tokens consumed by all models over the period.',
  'Est. Cost': 'Estimated spend for the period, based on per-model token pricing.',
}

export function buildInsights(accent = ACCENT): InsightsData {
  const days = [12, 18, 9, 22, 16, 28, 24, 31, 19, 26, 33, 21, 29, 38]
  const dmax = Math.max(...days)
  const kpiRaw = [
    { label: 'Sessions', value: '128', accent: '#5aa2f0' },
    { label: 'Messages', value: '1.4k', accent: '#2dd4bf' },
    { label: 'Tokens', value: '9.7M', accent },
    { label: 'Est. Cost', value: '$42.18', accent: '#9b8cff' },
  ]
  return {
    period: 'Last 30 days',
    kpis: kpiRaw.map((k) => ({
      ...k,
      info: {
        category: 'Insights · Last 30 days',
        title: k.label,
        value: k.value,
        accent: k.accent,
        desc: KPI_BLURB[k.label],
        stats: [
          { label: 'Value', value: k.value },
          { label: 'Period', value: 'Last 30 days' },
        ],
      },
    })),
    days: days.map((v) => ({
      h: Math.round(14 + (v / dmax) * 72) + 'px',
      bg: `color-mix(in oklab, ${accent} ${Math.round(34 + (v / dmax) * 66)}%, transparent)`,
    })),
    peak: '14:00',
    tokInPct: '63%',
    tokOutPct: '37%',
    tokIn: '6.1M',
    tokOut: '3.6M',
    tokTotal: '9.7M',
    models: [
      { name: 'Claude Sonnet 4.6', sessions: '86', tokens: '6.8M', cost: '$30.10', share: '70%', color: '#f6b73c' },
      { name: 'Claude Haiku 4', sessions: '34', tokens: '2.1M', cost: '$7.40', share: '22%', color: '#5aa2f0' },
      { name: 'Claude Opus 4', sessions: '8', tokens: '0.8M', cost: '$4.68', share: '8%', color: '#9b8cff' },
    ],
    skills: [
      { skill: 'web-fetch', uses: '142', share: '34%', w: '100%' },
      { skill: 'kanban', uses: '98', share: '23%', w: '69%' },
      { skill: 'obsidian', uses: '71', share: '17%', w: '50%' },
      { skill: 'gpu-bench', uses: '54', share: '13%', w: '38%' },
      { skill: 'etl', uses: '55', share: '13%', w: '39%' },
    ],
    activityInfo: {
      category: 'Insights · Chart',
      title: 'Activity by Day',
      accent,
      desc: 'Daily task volume over the last 30 days. Use it to spot cadence — build days, quiet weekends, and spikes around releases.',
      stats: [
        { label: 'Period', value: 'Last 30 days' },
        { label: 'Peak hour', value: '14:00' },
      ],
    },
    tokenInfo: {
      category: 'Insights · Chart',
      title: 'Token Breakdown',
      accent: '#2dd4bf',
      desc: 'Split of input versus output tokens across all models for the period.',
      stats: [
        { label: 'Input', value: '6.1M · 63%' },
        { label: 'Output', value: '3.6M · 37%' },
        { label: 'Total', value: '9.7M' },
      ],
    },
    modelsInfo: {
      category: 'Insights · Table',
      title: 'Models',
      accent: '#5aa2f0',
      desc: 'Per-model usage: sessions, tokens consumed, estimated cost, and share of total spend.',
      stats: [
        { label: 'Claude Sonnet 4.6', value: '70% · $30.10' },
        { label: 'Claude Haiku 4', value: '22% · $7.40' },
        { label: 'Claude Opus 4', value: '8% · $4.68' },
      ],
    },
    skillsInfo: {
      category: 'Insights · Chart',
      title: 'Skill Usage',
      accent: '#9b8cff',
      desc: 'Which skills the agents called most over the period. web-fetch dominates, reflecting heavy grounding in live external sources.',
      stats: [
        { label: 'Top skill', value: 'web-fetch · 142' },
        { label: 'Tracked skills', value: '5' },
      ],
    },
  }
}

// ---------------------------------------------------------------------------
// Sessions panel
// ---------------------------------------------------------------------------

export interface SessionRow {
  id: string
  title: string
  worker: string
  tenant: string
  status: 'running' | 'idle' | 'done' | 'error'
  ageSec: number
  tokens: number
  model: string
}

const SESSIONS_RAW: SessionRow[] = [
  { id: '4118', title: 'Benchmark RVC models on the 3070', worker: 'executor', tenant: 'dm-voice-board', status: 'running', ageSec: 2400, tokens: 184200, model: 'Claude Sonnet 4.6' },
  { id: '4203', title: 'Nightly export to S3', worker: 'coder-c', tenant: 'atlas-crm', status: 'running', ageSec: 1200, tokens: 96400, model: 'Claude Sonnet 4.6' },
  { id: '4096', title: 'Triage latency reports', worker: 'swarm-worker-b', tenant: 'dm-voice-board', status: 'idle', ageSec: 5400, tokens: 12800, model: 'Claude Haiku 4' },
  { id: '2041', title: 'Design spec: real-time RVC pipeline', worker: 'coder-d', tenant: 'dm-voice-board', status: 'done', ageSec: 25200, tokens: 271500, model: 'Claude Sonnet 4.6' },
  { id: '3990', title: 'Rotate API keys', worker: 'coder-e', tenant: 'internal', status: 'error', ageSec: 8600, tokens: 4200, model: 'Claude Sonnet 4.6' },
  { id: '1990', title: 'Contact dedupe job', worker: 'coder-c', tenant: 'atlas-crm', status: 'done', ageSec: 30000, tokens: 142000, model: 'Claude Sonnet 4.6' },
]

const SESS_META: Record<SessionRow['status'], { l: string; c: string }> = {
  running: { l: 'Running', c: '#2dd4bf' },
  idle: { l: 'Idle', c: '#5aa2f0' },
  done: { l: 'Done', c: '#4ade80' },
  error: { l: 'Error', c: '#fb6f6f' },
}

const TENANT_ICON: Record<string, string> = {
  'dm-voice-board': '❖',
  'atlas-crm': '▣',
  internal: '⬢',
}

function fmtDur(sec: number): string {
  if (sec < 60) return sec + 's'
  if (sec < 3600) return Math.round(sec / 60) + 'm'
  return Math.round(sec / 360) / 10 + 'h'
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

export interface SessionView {
  id: string
  title: string
  worker: string
  tenant: string
  icon: string
  model: string
  statusKey: SessionRow['status']
  statusLabel: string
  statusColor: string
  age: string
  tokens: string
}

export function buildSessions() {
  const sessions: SessionView[] = SESSIONS_RAW.map((x) => {
    const m = SESS_META[x.status]
    return {
      id: x.id,
      title: x.title,
      worker: x.worker,
      tenant: x.tenant,
      icon: TENANT_ICON[x.tenant] || '◆',
      model: x.model,
      statusKey: x.status,
      statusLabel: m.l,
      statusColor: m.c,
      age: fmtDur(x.ageSec),
      tokens: fmtTokens(x.tokens),
    }
  })
  const summary = {
    running: SESSIONS_RAW.filter((x) => x.status === 'running').length,
    idle: SESSIONS_RAW.filter((x) => x.status === 'idle').length,
    done: SESSIONS_RAW.filter((x) => x.status === 'done').length,
    error: SESSIONS_RAW.filter((x) => x.status === 'error').length,
  }
  const statuses: SessionRow['status'][] = ['running', 'idle', 'done', 'error']
  return { sessions, summary, statuses, statusMeta: SESS_META }
}

// ---------------------------------------------------------------------------
// Logs panel
// ---------------------------------------------------------------------------

export type LogLevel = 'info' | 'warning' | 'error' | 'debug'

export interface LogEntry {
  id: string
  ts: string
  level: LogLevel
  service: string
  message: string
  duration: string
  status: string
  tags: string[]
}

export const LOGS: LogEntry[] = [
  { id: '1', ts: '2026-06-18T14:32:45Z', level: 'info', service: 'dispatcher', message: 'Dispatched task t8 → executor', duration: '245ms', status: 'ok', tags: ['dispatch', 'run'] },
  { id: '2', ts: '2026-06-18T14:32:42Z', level: 'warning', service: 'kanban-db', message: 'WAL checkpoint contention detected', duration: '1.2s', status: 'warn', tags: ['sqlite', 'perf'] },
  { id: '3', ts: '2026-06-18T14:32:40Z', level: 'error', service: 'executor', message: 'GPU OOM during model 3 benchmark', duration: '5.1s', status: '503', tags: ['gpu', 'error'] },
  { id: '4', ts: '2026-06-18T14:32:38Z', level: 'info', service: 'gateway', message: 'Session created for default profile', duration: '156ms', status: '201', tags: ['auth', 'session'] },
  { id: '5', ts: '2026-06-18T14:32:36Z', level: 'debug', service: 'memory', message: 'vector_search · 3 matches · cosine>0.82', duration: '38ms', status: 'ok', tags: ['memory', 'search'] },
  { id: '6', ts: '2026-06-18T14:32:35Z', level: 'info', service: 'coder-c', message: 'Nightly S3 export committed · 1.2M rows', duration: '3.4s', status: 'ok', tags: ['etl', 's3'] },
  { id: '7', ts: '2026-06-18T14:32:32Z', level: 'error', service: 'memory', message: 'Mem0 provider unreachable', duration: '2.3s', status: '502', tags: ['memory', 'error'] },
  { id: '8', ts: '2026-06-18T14:32:30Z', level: 'info', service: 'kanban-db', message: 'Task t1 promoted → ready', duration: '120ms', status: 'ok', tags: ['kanban'] },
  { id: '9', ts: '2026-06-18T14:32:28Z', level: 'warning', service: 'dispatcher', message: 'No idle workers for 3 ready tasks', duration: '145ms', status: '429', tags: ['dispatch', 'warn'] },
  { id: '10', ts: '2026-06-18T14:32:25Z', level: 'debug', service: 'gateway', message: 'SSE poll cycle · 0.3s · 2 subscribers', duration: '12ms', status: 'ok', tags: ['sse', 'poll'] },
]

export const LOG_LEVELS: LogLevel[] = ['info', 'warning', 'error', 'debug']

export function logLevelStyle(l: LogLevel): { bg: string; c: string } {
  return (
    {
      info: { bg: 'rgba(90,162,240,0.12)', c: '#8fb4ec' },
      warning: { bg: 'rgba(246,183,60,0.12)', c: '#f6b73c' },
      error: { bg: 'rgba(251,111,111,0.12)', c: '#fb6f6f' },
      debug: { bg: 'rgba(155,140,255,0.12)', c: '#9b8cff' },
    } as const
  )[l]
}

export function logStatusColor(s: string): string {
  if (s === 'ok' || s === '200' || s === '201') return '#4ade80'
  if (s === 'warn' || s === '429') return '#f6b73c'
  return '#fb6f6f'
}

// ---------------------------------------------------------------------------
// Settings panel
// ---------------------------------------------------------------------------

export const ACCENT_SWATCHES = ['#f6b73c', '#2dd4bf', '#9b8cff', '#5aa2f0', '#4ade80']

export interface ToggleDef {
  key: string
  label: string
  desc: string
  default: boolean
}

export const SETTINGS_TOGGLES: ToggleDef[] = [
  { key: 'setStream', label: 'Stream activity', desc: 'Show tool calls and reasoning live as the agent works.', default: true },
  { key: 'setEndless', label: 'Endless scroll', desc: 'Auto-load older messages when you reach the top.', default: true },
  { key: 'setAutoApprove', label: 'Auto-approve safe tools', desc: 'Run read-only tools without a confirmation prompt.', default: false },
  { key: 'setNotify', label: 'Desktop notifications', desc: 'Notify when a long-running session finishes.', default: true },
  { key: 'setUpdates', label: 'Check for updates', desc: 'Notify when a new Hermes or agent build is available.', default: true },
  { key: 'setInsights', label: 'Sync to Insights', desc: 'Send anonymized usage metrics to the Insights dashboard.', default: false },
  { key: 'setRedact', label: 'Redact secrets in logs', desc: 'Mask API keys and tokens in request/response logs.', default: true },
  { key: 'setCliSessions', label: 'Show CLI sessions', desc: 'Merge CLI and TUI sessions into the conversation sidebar.', default: false },
]

export const LANG_OPTS = [
  { value: 'en', label: 'English' },
  { value: 'es', label: 'Español' },
  { value: 'fr', label: 'Français' },
  { value: 'de', label: 'Deutsch' },
  { value: 'ja', label: '日本語' },
]
export const API_KEYS = [
  { label: 'Anthropic API key', value: 'sk-ant-api03-7f3c9d2e8b1a4f6c5d0e9a8b' },
  { label: 'OpenAI API key', value: 'sk-proj-2a9f8e7d6c5b4a3f1e0d9c8b' },
  { label: 'AWS access key', value: 'AKIA4XYZ7QWE2RTY8UIO' },
]

// ---------------------------------------------------------------------------
// Memory Galaxy — node field
// ---------------------------------------------------------------------------

export interface MemNode {
  id: string
  tier: string
  tierLabel: string
  color: string
  title: string
  importance: number
  ageDays: number
  recall: number
  x: number
  y: number
  z: number
  label?: boolean
}

export interface MemTier {
  id: string
  label: string
  color: string
  count: number
}

export interface GalaxyData {
  nodes: MemNode[]
  links: [number, number][]
  tiers: MemTier[]
}

const GALAXY_TIERS = [
  { id: 'notes', label: 'Notes', color: '#f6b73c', c: [-2.5, 0.6, 0.5], titles: ['Latency gate is the gate', 'Audio routing via VB-Cable', 'Friday build cadence', 'Feedback loop risk', 'Playtester latency reports', 'Keep Fridays for cutting builds', 'Hero NPC gated on POC', 'Room treatment notes', 'Headset isolation tip', 'RVC warm-up time', 'Stage mic levels', 'Backup voice profiles'] },
  { id: 'profile', label: 'User Profile', color: '#5aa2f0', c: [2.4, 0.9, -0.8], titles: ['Role: DM & board owner', 'Hardware: RTX 3070 laptop', 'Workers: Local host + Mini', 'Style: terse, decisive', 'Prefers GO/NO-GO gates', 'Timezone: America/Chicago', 'Evening sessions', 'Final say on gates'] },
  { id: 'soul', label: 'Agent Soul', color: '#9b8cff', c: [0.2, 2.3, 0.9], titles: ['Tone: direct and calm', 'Answer first, explain if asked', 'Surface blockers early', 'Never start gated work early', 'Reliability over features', 'Prove before building', 'Mission-control voice', 'No filler, no hype'] },
  { id: 'context', label: 'Project Context', color: '#2dd4bf', c: [0.6, -2.1, -0.6], titles: ['Project: dm-voice-board', 'Realtime RVC NPC voices', 'Done = live under latency gate', 'No feedback loop allowed', 'Tenant: dm-voice-board', 'Tenant: atlas-crm', 'Tenant: internal', 'Six-stage pipeline', 'Capture -> train -> route', 'Weekly playtest loop', '3 hero NPCs planned', 'Branch: poc/latency-gate'] },
  { id: 'facts', label: 'Knowledge', color: '#4ade80', c: [-1.4, -1.1, 2.3], titles: ['RVC latency on 3070', 'VB-Cable buffer size', 'S3 cold bucket region', 'Python 3.12 rollout', 'Webhook backoff policy', 'Tenant timezone defaults', 'Dispatcher claim TTL', 'Skill: voice-rt', 'Skill: gpu-bench', 'Skill: etl', 'Kanban column model', 'Run outcome: reclaimed', 'SQLite WAL + connect_closing', 'SSE 0.3s poll', 'Honcho provider', 'Obsidian vault index'] },
  { id: 'convos', label: 'Conversations', color: '#fb6f6f', c: [2.1, -0.5, 2.0], titles: ['Re: timezone bug decision', 'Re: hero NPC scope', 'Memory stores summary', 'Re: latency gate sign-off', 'Re: nightly S3 export', 'Re: key rotation cadence', 'Re: dialogue trees', 'Playtest #1 recap', 'Re: worker pool upgrade', 'Re: dedupe job', 'Incident postmortem chat', 'Re: mic routing', 'Re: benchmark results', 'Onboarding walkthrough'] },
]

/** Deterministic galaxy data — same seed/structure as the prototype. */
export function buildGalaxy(): GalaxyData {
  let seed = 20240617
  const rnd = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff
    return seed / 0x7fffffff
  }
  const gas = () => (rnd() + rnd() + rnd() - 1.5) * 0.95
  const nodes: MemNode[] = []
  let id = 0
  for (const t of GALAXY_TIERS) {
    for (const title of t.titles) {
      const imp = 0.4 + rnd() * 0.6
      const sp = 1.55 - imp * 0.5
      nodes.push({
        id: 'm' + id++,
        tier: t.id,
        tierLabel: t.label,
        color: t.color,
        title,
        importance: imp,
        ageDays: Math.round(2 + rnd() * 180),
        recall: Math.max(35, Math.round(imp * 100 - rnd() * 14)),
        x: t.c[0] * 0.6 + gas() * sp,
        y: t.c[1] * 0.6 + gas() * sp,
        z: t.c[2] * 0.6 + gas() * sp,
      })
    }
  }
  // nearest-3 links
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
    for (let k = 0; k < 3; k++) {
      const j = ds[k][1]
      const key = i < j ? i + '-' + j : j + '-' + i
      if (!seen.has(key)) {
        seen.add(key)
        links.push([i, j])
      }
    }
  }
  // label the most-important node per tier
  const bestByTier: Record<string, number> = {}
  nodes.forEach((m, idx) => {
    if (bestByTier[m.tier] === undefined || nodes[bestByTier[m.tier]].importance < m.importance) bestByTier[m.tier] = idx
  })
  Object.values(bestByTier).forEach((idx) => {
    nodes[idx].label = true
  })
  const tiers: MemTier[] = GALAXY_TIERS.map((t) => ({ id: t.id, label: t.label, color: t.color, count: t.titles.length }))
  return { nodes, links, tiers }
}

export interface GalaxySelection {
  id: string
  title: string
  detail: string
  color: string
  tierLabel: string
  importance: string
  recall: string
  age: string
}

export function galaxyDecor(m: MemNode): GalaxySelection {
  const band =
    m.importance > 0.78
      ? 'Core memory — frequently recalled across sessions.'
      : m.importance > 0.55
        ? 'Recalled when the current context matches.'
        : 'Rarely surfaced; kept for completeness.'
  return {
    id: m.id,
    title: m.title,
    detail: band,
    color: m.color,
    tierLabel: m.tierLabel,
    importance: m.importance.toFixed(2),
    recall: m.recall + '%',
    age: m.ageDays + 'd',
  }
}
