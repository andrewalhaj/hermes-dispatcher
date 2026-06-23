import { useEffect, useRef, useState } from 'react'

export interface SysDataPoint {
  value: number
  isSpike: boolean
}

export interface SysMetric {
  key: string
  label: string
  color: string
  unit: string
  /** Current value (already display-rounded). */
  cur: number
  /** Rolling buffer of points, oldest → newest. */
  data: SysDataPoint[]
  /** True when any point in the window is a spike. */
  hasSpike: boolean
  /** True when the metric is unavailable (e.g. GPU on a non-NVIDIA host). */
  unavailable: boolean
}

export interface AgentMem {
  name: string
  rss_mb: number
  data: SysDataPoint[]
  color: string
}

export interface SystemStats {
  metrics: SysMetric[]
  /** System memory % (current). */
  memPct: number
  /** Rolling system-memory % buffer for the dedicated sparkline. */
  memData: SysDataPoint[]
  memUsedGb: number
  memTotalGb: number
  agents: AgentMem[]
  hasAnySpike: boolean
  hostLabel: string
}

interface SystemApi {
  cpu_pct: number
  mem_pct: number
  mem_used_gb: number
  mem_total_gb: number
  disk_pct: number
  net_mbps: number
  gpu_pct: number | null
  vram_pct: number | null
  agent_memory: { name: string; rss_mb: number }[]
  running_agents: { name: string; tasks: number }[]
}

const EMPTY: SystemApi = {
  cpu_pct: 0,
  mem_pct: 0,
  mem_used_gb: 0,
  mem_total_gb: 0,
  disk_pct: 0,
  net_mbps: 0,
  gpu_pct: null,
  vram_pct: null,
  agent_memory: [],
  running_agents: [],
}

const LEN = 20
const AGENT_LEN = 15
const POLL_MS = 3000

const PALETTE = ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#2dd4bf']

/** Percentage-style spike: a sustained-high reading. */
const pctSpike = (v: number) => v > 70
/** Network spike: a sudden surge relative to a soft ceiling (MB/s). */
const netSpike = (v: number) => v > 50

function pushBuf(buf: number[], v: number, len: number): number[] {
  const next = [...buf, v]
  return next.length > len ? next.slice(next.length - len) : next
}

function toPoints(buf: number[], spikeFn: (v: number) => boolean): SysDataPoint[] {
  return buf.map((value) => ({ value, isSpike: spikeFn(value) }))
}

/**
 * Polls /api/system every 3s and accumulates rolling sparkline buffers with
 * spike detection. GPU/VRAM degrade to `unavailable` when the backend reports
 * null (non-NVIDIA host).
 */
export function useSystemStats(): SystemStats {
  const cpu = useRef<number[]>([])
  const gpu = useRef<number[]>([])
  const vram = useRef<number[]>([])
  const net = useRef<number[]>([])
  const mem = useRef<number[]>([])
  const agentBufs = useRef<Map<string, number[]>>(new Map())
  const [snap, setSnap] = useState<SystemApi>(EMPTY)

  useEffect(() => {
    let cancelled = false

    async function tick() {
      try {
        const res = await fetch('/api/system')
        if (!res.ok) return
        const json = (await res.json()) as SystemApi
        if (cancelled) return

        cpu.current = pushBuf(cpu.current, json.cpu_pct, LEN)
        gpu.current = pushBuf(gpu.current, json.gpu_pct ?? 0, LEN)
        vram.current = pushBuf(vram.current, json.vram_pct ?? 0, LEN)
        net.current = pushBuf(net.current, json.net_mbps, LEN)
        mem.current = pushBuf(mem.current, json.mem_pct, LEN)

        const seen = new Set<string>()
        for (const a of json.agent_memory) {
          seen.add(a.name)
          const prev = agentBufs.current.get(a.name) ?? []
          agentBufs.current.set(a.name, pushBuf(prev, a.rss_mb, AGENT_LEN))
        }
        // Drop agents that disappeared.
        for (const k of Array.from(agentBufs.current.keys())) {
          if (!seen.has(k)) agentBufs.current.delete(k)
        }

        setSnap(json)
      } catch {
        // keep last good data on error
      }
    }

    tick()
    const id = setInterval(tick, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  const gpuUnavailable = snap.gpu_pct === null
  const vramUnavailable = snap.vram_pct === null

  const metrics: SysMetric[] = [
    {
      key: 'cpu',
      label: 'CPU',
      color: '#3b82f6',
      unit: '%',
      cur: snap.cpu_pct,
      data: toPoints(cpu.current, pctSpike),
      hasSpike: cpu.current.some(pctSpike),
      unavailable: false,
    },
    {
      key: 'gpu',
      label: 'GPU',
      color: '#10b981',
      unit: '%',
      cur: snap.gpu_pct ?? 0,
      data: gpuUnavailable ? [] : toPoints(gpu.current, pctSpike),
      hasSpike: !gpuUnavailable && gpu.current.some(pctSpike),
      unavailable: gpuUnavailable,
    },
    {
      key: 'vram',
      label: 'VRAM',
      color: '#f59e0b',
      unit: '%',
      cur: snap.vram_pct ?? 0,
      data: vramUnavailable ? [] : toPoints(vram.current, pctSpike),
      hasSpike: !vramUnavailable && vram.current.some(pctSpike),
      unavailable: vramUnavailable,
    },
    {
      key: 'network',
      label: 'Network',
      color: '#8b5cf6',
      unit: 'MB/s',
      cur: snap.net_mbps,
      data: toPoints(net.current, netSpike),
      hasSpike: net.current.some(netSpike),
      unavailable: false,
    },
  ]

  const memData = toPoints(mem.current, pctSpike)

  const agents: AgentMem[] = snap.agent_memory.map((a, i) => ({
    name: a.name,
    rss_mb: a.rss_mb,
    color: PALETTE[i % PALETTE.length],
    data: (agentBufs.current.get(a.name) ?? []).map((v) => ({ value: v, isSpike: false })),
  }))

  const hasAnySpike =
    metrics.some((m) => m.hasSpike) || memData.some((d) => d.isSpike)

  return {
    metrics,
    memPct: snap.mem_pct,
    memData,
    memUsedGb: snap.mem_used_gb,
    memTotalGb: snap.mem_total_gb,
    agents,
    hasAnySpike,
    hostLabel: 'Local host',
  }
}
