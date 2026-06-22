import { useEffect, useRef, useState } from 'react'

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

export interface SystemMonitor {
  hostLabel: string
  metrics: MetricView[]
  mem: { cur: string; line: string; area: string; fill: string }
}

const LEN = 14

const mkPath = (arr: number[], max: number): SparkPaths => {
  const n = arr.length
  const W = 100
  const H = 30
  const pts = arr.map((v, i) => [(n > 1 ? i / (n - 1) : 0) * W, H - (Math.min(v, max) / max) * H])
  const line = 'M ' + pts.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' L ')
  return { line, area: `${line} L ${W} ${H} L 0 ${H} Z` }
}

const makeMetric = (key: string, label: string, color: string, unit: string, arr: number[]): MetricView => {
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

/** Consumes real system metrics from the overview API and accumulates rolling sparkline buffers. */
export function useSystemMonitor(system: { cpu_pct: number; mem_pct: number; disk_pct: number }): SystemMonitor {
  const cpuBuf = useRef<number[]>(Array(LEN).fill(0))
  const memBuf = useRef<number[]>(Array(LEN).fill(0))
  const diskBuf = useRef<number[]>(Array(LEN).fill(0))
  const [, setTick] = useState(0)

  useEffect(() => {
    cpuBuf.current = [...cpuBuf.current.slice(1), system.cpu_pct]
    memBuf.current = [...memBuf.current.slice(1), system.mem_pct]
    diskBuf.current = [...diskBuf.current.slice(1), system.disk_pct]
    setTick((t) => t + 1)
  }, [system.cpu_pct, system.mem_pct, system.disk_pct])

  const memArr = memBuf.current
  const memCur = memArr[memArr.length - 1] ?? 0
  const memPath = mkPath(memArr, 100)

  return {
    hostLabel: 'Local host',
    metrics: [
      makeMetric('cpu', 'CPU', '#5aa2f0', '%', cpuBuf.current),
      makeMetric('disk', 'Disk', '#9b8cff', '%', diskBuf.current),
    ],
    mem: {
      cur: memCur.toFixed(0),
      line: memPath.line,
      area: memPath.area,
      fill: 'color-mix(in oklab, #fb6f6f 20%, transparent)',
    },
  }
}
