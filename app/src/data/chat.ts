import type { Message, PastSession, PlanStep, PlanStepStatus } from './types'
import { ACCENT } from './agents'

/** Current time as a short clock string, e.g. "2:14 PM". */
export function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true })
}

/** Canned worker replies (non-Hermes agents answer after a 1.5s delay). */
const CANNED: Record<string, string> = {
  hermes: 'On it — routing that now.',
  'executor': 'Queued on the GPU; I’ll report latency when the run completes.',
  'coder-c': 'Kicked off the ETL pass — watching for row errors.',
  'coder-d': 'Drafting that content now.',
  'coder-e': 'Acknowledged — running the infra check.',
}

export function cannedReply(key: string): string {
  return CANNED[key] || 'Acknowledged.'
}

/** Convert epoch seconds to a human-readable "when" string for past sessions. */
export function epochToWhen(epochSecs: number): string {
  const d = new Date(epochSecs * 1000)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000)
  const timeStr = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', hour12: true })
  if (diffDays === 0) return `Today · ${timeStr}`
  if (diffDays === 1) return `Yesterday · ${timeStr}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' · ' + timeStr
}

/** Composer dropdown option lists. */
export const PROFILE_OPTIONS = ['default', 'reviewer', 'coder-e']
export const FOLDER_OPTIONS = ['Home', 'workspace', 'docs', 'archive']
export const MODEL_OPTIONS = ['Claude Sonnet 4.6', 'Claude Haiku 4', 'Claude Opus 4']
export const REASON_OPTIONS = ['minimal', 'low', 'medium', 'high', 'xhigh']

/** The static 5-step dispatch plan reproduced from the prototype. */
export function planSteps(accent = ACCENT): PlanStep[] {
  return [
    {
      id: '1',
      title: 'Analyze dispatch request',
      status: 'success',
      duration: '0.4s',
      detail: {
        boxBg: 'rgba(8,11,17,0.5)',
        boxBorder: 'rgba(255,255,255,0.07)',
        lead: { kind: 'check', text: 'Parsed operator intent — route to the worker pool', color: '#4ade80' },
        lines: [
          { label: 'Channel', value: 'dm-voice-board' },
          { label: 'Target', value: 'executor' },
          { label: 'Gate', value: 'latency < 220ms', valueColor: '#f6b73c' },
        ],
      },
    },
    {
      id: '2',
      title: 'Search skills & memory',
      status: 'success',
      duration: '1.2s',
      detail: {
        boxBg: 'rgba(8,11,17,0.5)',
        boxBorder: 'rgba(255,255,255,0.07)',
        lead: { kind: 'check', text: 'vector_search · 3 matches retrieved', color: '#4ade80' },
        lines: [
          { text: '• voice-rt — realtime RVC conversion', color: '#9298ab' },
          { text: '• gpu-bench — 3070 latency profile', color: '#9298ab' },
          { text: '• obsidian — latency-gate notes', color: '#9298ab' },
        ],
      },
    },
    {
      id: '3',
      title: 'Synthesize execution plan',
      status: 'active',
      duration: '…',
      defaultExpanded: true,
      detail: {
        boxBg: '#070a0f',
        boxBorder: 'rgba(255,255,255,0.07)',
        lead: { kind: 'spinner', text: 'Composing the dispatch sequence…', color: '#8fb4ec' },
        lines: [
          { text: 'const plan = claim(readyTasks)', color: '#9b8cff' },
          { text: '→ reserve GPU on executor', color: '#9298ab', indent: 14 },
          { text: '→ warm RVC model (cold start ≈ 6s)', color: '#9298ab', indent: 14 },
          { text: '→ stream latency → kanban-db ▌', color: accent, indent: 14 },
        ],
      },
    },
    {
      id: '4',
      title: 'Check worker availability',
      status: 'error',
      duration: '0.8s',
      detail: {
        boxBg: 'rgba(251,111,111,0.08)',
        boxBorder: 'rgba(251,111,111,0.22)',
        lines: [
          { text: 'Warning · capacity contention', color: '#fb6f6f' },
          {
            text: 'No idle workers for 3 ready tasks; executor hit GPU OOM on model 3. Re-queuing behind the latency-gate run.',
            color: 'rgba(251,111,111,0.82)',
          },
        ],
      },
    },
    { id: '5', title: 'Dispatch to worker', status: 'pending' },
  ]
}

/** Ring background / foreground color per step status. */
export function planStatusMeta(status: PlanStepStatus, accent: string): { ringBg: string; ringColor: string } {
  switch (status) {
    case 'success':
      return { ringBg: 'rgba(74,222,128,0.16)', ringColor: '#4ade80' }
    case 'active':
      return { ringBg: `color-mix(in oklab, ${accent} 22%, transparent)`, ringColor: accent }
    case 'error':
      return { ringBg: 'rgba(251,111,111,0.16)', ringColor: '#fb6f6f' }
    default:
      return { ringBg: 'rgba(255,255,255,0.06)', ringColor: '#6a7088' }
  }
}

/** Seed threads keyed by agent. */
export const INITIAL_THREADS: Record<string, Message[]> = {
  hermes: [
    {
      id: 'h1',
      role: 'user',
      text: 'Can you look through all the different memory stores Hermes can reach and summarise what each is for?',
      at: '2:11 PM',
    },
    {
      id: 'h2',
      role: 'agent',
      text: 'Done — built-in, the Supabase knowledge store, and the Obsidian vault are all connected. The full breakdown is in docs/hermes-memory-stores.md if you want the details.',
      at: '2:14 PM',
    },
  ],
  'executor': [
    { id: 'r1', role: 'agent', text: 'Benchmarking model 2 of 4 on the 3070 — latency holding under the gate so far.', at: '1:48 PM' },
  ],
  'coder-c': [{ id: 'a1', role: 'agent', text: 'Nightly S3 export running · 1.2M rows queued.', at: '1:20 PM' }],
  'coder-d': [],
  'coder-e': [],
}

/** Past chat sessions keyed by agent. */
export const PAST_SESSIONS: Record<string, PastSession[]> = {
  hermes: [
    {
      id: 'hs1',
      title: 'Memory store audit',
      when: 'Yesterday · 4:02 PM',
      msgs: [
        { role: 'user', text: 'Which memory stores are actually connected right now?', at: '4:02 PM' },
        { role: 'agent', text: 'Three: the built-in store, the Supabase knowledge store, and the Obsidian vault. Mem0 is configured but disabled.', at: '4:03 PM' },
        { role: 'user', text: 'Disable Mem0 for now, it is noisy.', at: '4:05 PM' },
        { role: 'agent', text: 'Done — Mem0 is off. Reads now fall back to built-in + Obsidian.', at: '4:05 PM' },
      ],
    },
    {
      id: 'hs2',
      title: 'Latency gate sign-off',
      when: 'Jun 14 · 11:20 AM',
      msgs: [
        { role: 'user', text: 'Did the 3070 latency test pass?', at: '11:20 AM' },
        { role: 'agent', text: 'Yes — round-trip held at 178ms, under the 220ms gate. t1 is green; t2 is unblocked.', at: '11:21 AM' },
      ],
    },
  ],
  'executor': [
    {
      id: 'rs1',
      title: 'Model 1 benchmark',
      when: 'Jun 16 · 9:10 AM',
      msgs: [{ role: 'agent', text: 'Model 1 of 4 done: 192ms p50, 240ms p95. Slightly over gate at p95.', at: '9:10 AM' }],
    },
  ],
  'coder-c': [
    {
      id: 'as1',
      title: 'Dedupe dry-run',
      when: 'Jun 15 · 2:30 AM',
      msgs: [{ role: 'agent', text: 'Dry-run merged 4,210 duplicate contacts across 3 lists. Awaiting confirm to commit.', at: '2:30 AM' }],
    },
  ],
  'coder-d': [],
  'coder-e': [
    {
      id: 'os1',
      title: 'py3.12 rollout',
      when: 'Jun 10 · 6:00 PM',
      msgs: [{ role: 'agent', text: 'All 5 workers rolled to Python 3.12 and redeployed. Health checks green.', at: '6:02 PM' }],
    },
  ],
}
