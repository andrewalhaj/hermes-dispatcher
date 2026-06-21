import { useEffect, useRef, useState } from 'react'
import { CHAT_AGENTS } from '../../data/agents'

export type MachineId = 'studio' | 'mini'

export interface SparkPaths {
  line: string
  area: string
}

export interface MetricView {
  key: string
  label: string
  color: string
  unit: string
  cur: string
  line: string
  area: string
  fill: string
  stroke: string
  dot: string
  valColor: string
}

export interface AgentMemView {
  key: string
  name: string
  color: string
  cur: string
  line: string
  area: string
  fill: string
}

interface MachineBuffers {
  cpu: number[]
  gpu: number[]
  vram: number[]
  net: number[]
  mem: number[]
  agents: Record<string, number[]>
}

const LEN = 14

const seed = (base: number, varr: number, max: number): number[] => {
  const a: number[] = []
  let v = base
  for (let i = 0; i < LEN; i++) {
    v = Math.max(3, Math.min(max, v + (Math.random() - 0.5) * varr))
    a.push(v)
  }
  return a
}

const mach = (c: { cpu: number; gpu: number; vram: number; net: number; mem: number; a: number }): MachineBuffers => ({
  cpu: seed(c.cpu, 14, 100),
  gpu: seed(c.gpu, 14, 100),
  vram: seed(c.vram, 12, 100),
  net: seed(c.net, 18, 100),
  mem: seed(c.mem, 6, 128),
  agents: {
    hermes: seed(c.a, 30, 380),
    'rvc-runner': seed(c.a * 1.8, 50, 380),
    'atlas-etl': seed(c.a * 1.4, 45, 380),
    'npc-builder': seed(c.a * 0.75, 30, 380),
    'ops-bot': seed(c.a * 0.6, 25, 380),
  },
})

const initBuffers = (): Record<MachineId, MachineBuffers> => ({
  studio: mach({ cpu: 45, gpu: 58, vram: 66, net: 32, mem: 80, a: 130 }),
  mini: mach({ cpu: 34, gpu: 28, vram: 44, net: 18, mem: 46, a: 90 }),
})

/** Push a new point onto a buffer, drifting from the last value, clamped to [3, max]. */
const advance = (arr: number[], varr: number, max: number): number[] => {
  const last = arr[arr.length - 1] ?? max / 2
  const next = Math.max(3, Math.min(max, last + (Math.random() - 0.5) * varr))
  return [...arr.slice(1), next]
}

const mkPath = (arr: number[], max: number): SparkPaths => {
  const n = arr.length
  const W = 100
  const H = 30
  const pts = arr.map((v, i) => [(n > 1 ? i / (n - 1) : 0) * W, H - (Math.min(v, max) / max) * H])
  const line = 'M ' + pts.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' L ')
  return { line, area: `${line} L ${W} ${H} L 0 ${H} Z` }
}

export interface SystemMonitor {
  machine: MachineId
  machineLabel: string
  setMachine: (m: MachineId) => void
  metrics: MetricView[]
  mem: { cur: string; line: string; area: string; fill: string }
  agents: AgentMemView[]
}

const machineLabel = (m: MachineId) => (m === 'studio' ? 'Mac Studio' : 'Mac Mini')

/** Live system-monitor buffers updating on an interval, with cleanup on unmount. */
export function useSystemMonitor(): SystemMonitor {
  const [machine, setMachine] = useState<MachineId>('studio')
  const buffersRef = useRef<Record<MachineId, MachineBuffers>>(initBuffers())
  const [, setTick] = useState(0)

  useEffect(() => {
    const id = window.setInterval(() => {
      const all = buffersRef.current
      for (const key of ['studio', 'mini'] as MachineId[]) {
        const b = all[key]
        b.cpu = advance(b.cpu, 14, 100)
        b.gpu = advance(b.gpu, 14, 100)
        b.vram = advance(b.vram, 12, 100)
        b.net = advance(b.net, 18, 100)
        b.mem = advance(b.mem, 6, 128)
        for (const ak of Object.keys(b.agents)) {
          b.agents[ak] = advance(b.agents[ak], 50, 380)
        }
      }
      setTick((t) => t + 1)
    }, 1100)
    return () => window.clearInterval(id)
  }, [])

  const sm = buffersRef.current[machine]

  const metric = (key: keyof Omit<MachineBuffers, 'agents'>, label: string, color: string, unit: string): MetricView => {
    const arr = sm[key]
    const cur = arr[arr.length - 1] ?? 0
    const p = mkPath(arr, 100)
    const spike = cur > 82
    return {
      key,
      label,
      color,
      unit,
      cur: cur.toFixed(0),
      line: p.line,
      area: p.area,
      fill: `color-mix(in oklab, ${color} 20%, transparent)`,
      stroke: spike ? '#fb6f6f' : color,
      dot: spike ? '#fb6f6f' : color,
      valColor: spike ? '#fb6f6f' : '#e4e6ee',
    }
  }

  const memArr = sm.mem
  const memCur = memArr[memArr.length - 1] ?? 0
  const memPath = mkPath(memArr, 128)

  return {
    machine,
    machineLabel: machineLabel(machine),
    setMachine,
    metrics: [
      metric('cpu', 'CPU', '#5aa2f0', '%'),
      metric('gpu', 'GPU', '#4ade80', '%'),
      metric('vram', 'VRAM', '#f6b73c', '%'),
      metric('net', 'Network', '#9b8cff', 'MB/s'),
    ],
    mem: {
      cur: memCur.toFixed(1),
      line: memPath.line,
      area: memPath.area,
      fill: 'color-mix(in oklab, #fb6f6f 20%, transparent)',
    },
    agents: CHAT_AGENTS.map((a) => {
      const arr = sm.agents[a.key] ?? []
      const cur = arr[arr.length - 1] ?? 0
      const p = mkPath(arr, 380)
      return {
        key: a.key,
        name: a.name,
        color: a.color,
        cur: cur.toFixed(0),
        line: p.line,
        area: p.area,
        fill: `color-mix(in oklab, ${a.color} 22%, transparent)`,
      }
    }),
  }
}
