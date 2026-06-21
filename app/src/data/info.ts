/** A single label/value stat row inside the info drawer. */
export interface InfoStat {
  label: string
  value: string
}

/**
 * The shape every clickable tile/card/chart hands to `openInfo`.
 * Content is always tile-specific — no placeholder text.
 */
export interface InfoObject {
  category: string
  title: string
  accent: string
  value?: string
  desc: string
  stats: InfoStat[]
  actionLabel?: string
  onAction?: () => void
}

/** Per-tile explanatory copy for the universal info drawer. Mirrors the prototype's tileBlurb(). */
const BLURBS: Record<string, string> = {
  'Tasks Run':
    "Total tasks the dispatcher has claimed and run across every tenant. Open the board to see what's in flight versus done.",
  'Active Sessions':
    'Worker sessions executing right now. Each holds a GPU or CPU slot until its task completes or yields.',
  Tenants:
    'Distinct projects routing work through Hermes. Tasks, memory, and logs are all partitioned per tenant.',
  'Memory Items':
    'Long-term memories indexed across notes, context, knowledge, and conversations — explore them spatially in the Memory Galaxy.',
  Agents:
    'Registered worker agents in the fleet, each with its own skill profile and GPU/CPU affinity.',
  'Active now':
    'Agents currently executing a task. The rest are idle and available for dispatch.',
  'Tasks today':
    'Tasks completed by the fleet since midnight, summed across all agents.',
  'Success rate':
    'Share of tasks that finished without error or retry over the trailing window.',
  'Avg latency':
    'Mean end-to-end time from dispatch to first result across recent tasks.',
  Sessions: 'Chat and worker sessions opened in the selected period.',
  Messages: 'Total messages exchanged with Hermes and the worker agents.',
  Tokens: 'Combined input and output tokens consumed by all models in the period.',
  'Est. Cost': 'Estimated spend for the period, based on per-model token pricing.',
  CPU: 'Live processor utilization on the selected machine, sampled continuously.',
  GPU: 'Live graphics/compute utilization — the bottleneck for RVC and model inference.',
  VRAM: 'Video memory in use. Sustained highs risk OOM during model loads.',
  Network: 'Live network throughput in and out of the selected machine.',
}

export function tileBlurb(label: string): string {
  return BLURBS[label] || `${label} — a live metric tracked by the dispatcher.`
}
