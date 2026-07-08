import { useEffect, useRef, useState } from 'react'

interface SwarmNode {
  id: string
  label: string
  status: 'idle' | 'running'
  tasks: number
  running: number
}

interface SwarmEdge {
  source: string
  target: string
  weight: number
}

interface SwarmData {
  nodes: SwarmNode[]
  edges: SwarmEdge[]
}

interface NodePos {
  id: string
  x: number
  y: number
  vx: number
  vy: number
}

interface TooltipState {
  x: number
  y: number
  label: string
  status: 'idle' | 'running'
  tasks: number
}

interface SwarmCanvasProps {
  accent: string
}

interface SwarmStats {
  agents: number
  running: number
  tasks: number
}

const RUNNING_COLOR = '#f6b73c'
const IDLE_COLOR = 'rgba(255,255,255,0.28)'

function nodeRadius(tasks: number): number {
  return 8 + Math.min(tasks, 10) * 1.6
}

/** Force-directed graph of Hermes agent topology. Nodes = profiles, edges = task relationships. */
export default function SwarmCanvas({ accent }: SwarmCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const dataRef = useRef<SwarmData>({ nodes: [], edges: [] })
  const positionsRef = useRef<Map<string, NodePos>>(new Map())
  const [displayNodes, setDisplayNodes] = useState<SwarmNode[]>([])
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [stats, setStats] = useState<SwarmStats>({ agents: 0, running: 0, tasks: 0 })
  const frameRef = useRef(0)

  // Poll /api/swarm every 15s; keep last-known data on error.
  useEffect(() => {
    let cancelled = false

    const load = () => {
      fetch('/api/swarm')
        .then((r) => r.json())
        .then((data: SwarmData) => {
          if (cancelled || !data || !Array.isArray(data.nodes)) return
          dataRef.current = data
          setDisplayNodes(data.nodes)
        })
        .catch(() => {/* keep last known data */})
    }

    load()
    const id = window.setInterval(load, 15_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  // Force-directed simulation + draw loop.
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let raf = 0
    let stopped = false

    const draw = () => {
      if (stopped) return

      const w = canvas.clientWidth
      const h = canvas.clientHeight

      if (w >= 2 && h >= 2) {
        // HiDPI: back canvas with physical pixels, draw in CSS pixels.
        const dpr = window.devicePixelRatio || 1
        const pw = Math.round(w * dpr)
        const ph = Math.round(h * dpr)
        if (canvas.width !== pw || canvas.height !== ph) {
          canvas.width = pw
          canvas.height = ph
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

        const { nodes, edges } = dataRef.current
        const positions = positionsRef.current
        const MARGIN = 32
        const cx = w / 2
        const cy = h / 2

        // Reconcile positions: remove stale, seed new nodes near center.
        const activeIds = new Set(nodes.map((n) => n.id))
        for (const id of positions.keys()) {
          if (!activeIds.has(id)) positions.delete(id)
        }
        for (const node of nodes) {
          if (!positions.has(node.id)) {
            positions.set(node.id, {
              id: node.id,
              x: cx + (Math.random() - 0.5) * 60,
              y: cy + (Math.random() - 0.5) * 60,
              vx: 0,
              vy: 0,
            })
          }
        }

        // Simulation step.
        const posArr = Array.from(positions.values())
        const REPULSION = 3500
        const SPRING_REST = 110
        const SPRING_K = 0.002
        const GRAVITY = 0.004
        const DAMPING = 0.85

        for (let i = 0; i < posArr.length; i++) {
          const a = posArr[i]
          let fx = 0
          let fy = 0

          // Repulsion between every pair.
          for (let j = 0; j < posArr.length; j++) {
            if (i === j) continue
            const b = posArr[j]
            const dx = a.x - b.x
            const dy = a.y - b.y
            const d2 = dx * dx + dy * dy + 0.01
            const d = Math.sqrt(d2)
            fx += (dx / d) * (REPULSION / d2)
            fy += (dy / d) * (REPULSION / d2)
          }

          // Spring attraction along edges (log-scaled weight so heavy edges don't collapse).
          for (const e of edges) {
            let partnerId: string | null = null
            if (e.source === a.id) partnerId = e.target
            else if (e.target === a.id) partnerId = e.source
            if (!partnerId) continue
            const b = positions.get(partnerId)
            if (!b) continue
            const dx = b.x - a.x
            const dy = b.y - a.y
            const d = Math.hypot(dx, dy) || 1
            const force = SPRING_K * (d - SPRING_REST) * Math.log1p(e.weight)
            fx += (dx / d) * force
            fy += (dy / d) * force
          }

          // Gentle center gravity so isolated nodes stay visible.
          fx += (cx - a.x) * GRAVITY
          fy += (cy - a.y) * GRAVITY

          a.vx = (a.vx + fx) * DAMPING
          a.vy = (a.vy + fy) * DAMPING
          a.x += a.vx
          a.y += a.vy
          a.x = Math.max(MARGIN, Math.min(w - MARGIN, a.x))
          a.y = Math.max(MARGIN, Math.min(h - MARGIN, a.y))
        }

        ctx.clearRect(0, 0, w, h)

        // Edges first.
        for (const e of edges) {
          const src = positions.get(e.source)
          const tgt = positions.get(e.target)
          if (!src || !tgt) continue
          const alpha = Math.min(0.3, 0.06 + Math.min(e.weight, 5) * 0.04)
          ctx.globalAlpha = alpha
          ctx.strokeStyle = 'rgba(255,255,255,1)'
          ctx.lineWidth = 0.7
          ctx.beginPath()
          ctx.moveTo(src.x, src.y)
          ctx.lineTo(tgt.x, tgt.y)
          ctx.stroke()
        }
        ctx.globalAlpha = 1

        // Nodes + labels.
        let runningCount = 0
        let totalTasks = 0
        for (const node of nodes) {
          const pos = positions.get(node.id)
          if (!pos) continue
          const r = nodeRadius(node.tasks)
          const isRunning = node.status === 'running'
          if (isRunning) runningCount++
          totalTasks += node.tasks

          ctx.beginPath()
          ctx.arc(pos.x, pos.y, r, 0, 6.2832)
          ctx.fillStyle = isRunning ? RUNNING_COLOR : IDLE_COLOR
          ctx.globalAlpha = isRunning ? 0.9 : 0.6
          ctx.fill()
          ctx.globalAlpha = 1

          ctx.font = '10px monospace'
          ctx.fillStyle = 'rgba(255,255,255,0.45)'
          ctx.textAlign = 'center'
          ctx.fillText(node.label, pos.x, pos.y + r + 13)
        }
        ctx.globalAlpha = 1

        frameRef.current++
        if (frameRef.current % 20 === 0) {
          setStats({ agents: nodes.length, running: runningCount, tasks: totalTasks })
        }
      }

      raf = requestAnimationFrame(draw)
    }

    raf = requestAnimationFrame(draw)
    return () => {
      stopped = true
      cancelAnimationFrame(raf)
    }
  }, [])

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top

    const { nodes } = dataRef.current
    const positions = positionsRef.current
    let found: TooltipState | null = null

    for (const node of nodes) {
      const pos = positions.get(node.id)
      if (!pos) continue
      if (Math.hypot(pos.x - mx, pos.y - my) <= nodeRadius(node.tasks) + 4) {
        found = { x: mx, y: my, label: node.label, status: node.status, tasks: node.tasks }
        break
      }
    }
    setTooltip(found)
  }

  const handleMouseLeave = () => setTooltip(null)

  return (
    <div style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block', zIndex: 0 }}
      />

      {/* Legend — bottom-left */}
      <div style={{
        position: 'absolute',
        bottom: 14,
        left: 14,
        zIndex: 2,
        background: 'rgba(10,10,18,0.72)',
        backdropFilter: 'blur(6px)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 7,
        padding: '8px 10px',
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        pointerEvents: 'none',
        maxHeight: '60%',
        overflow: 'hidden',
      }}>
        {displayNodes.length === 0 ? (
          <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>No active agents</span>
        ) : (
          displayNodes.slice(0, 8).map((n) => (
            <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <svg width="10" height="10" viewBox="0 0 10 10" style={{ flexShrink: 0 }}>
                <circle cx="5" cy="5" r="3"
                  fill={n.status === 'running' ? RUNNING_COLOR : 'rgba(255,255,255,0.28)'}
                  opacity={n.status === 'running' ? 0.95 : 0.55}
                />
              </svg>
              <span style={{
                fontSize: 10,
                color: n.status === 'running' ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.4)',
                letterSpacing: '0.01em',
              }}>{n.label}</span>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.32)', marginLeft: 'auto', paddingLeft: 8 }}>
                {n.tasks}
              </span>
            </div>
          ))
        )}
      </div>

      {/* Stats overlay — top-right */}
      <div style={{
        position: 'absolute',
        top: 14,
        right: 14,
        zIndex: 2,
        background: 'rgba(10,10,18,0.72)',
        backdropFilter: 'blur(6px)',
        border: '1px solid rgba(255,255,255,0.07)',
        borderRadius: 7,
        padding: '7px 11px',
        pointerEvents: 'none',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}>
        <StatChip value={stats.agents} label="agents" accent={accent} />
        <div style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.1)' }} />
        <StatChip value={stats.running} label="running" accent="#4ade80" pulse={stats.running > 0} />
        <div style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.1)' }} />
        <StatChip value={stats.tasks} label="tasks" accent={accent} />
      </div>

      {/* Hover tooltip */}
      {tooltip && (
        <div style={{
          position: 'absolute',
          left: tooltip.x + 12,
          top: tooltip.y - 8,
          zIndex: 3,
          background: 'rgba(10,10,18,0.88)',
          backdropFilter: 'blur(8px)',
          border: '1px solid rgba(155,140,255,0.3)',
          borderRadius: 7,
          padding: '5px 10px',
          pointerEvents: 'none',
          whiteSpace: 'nowrap',
        }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: accent, letterSpacing: '0.01em' }}>{tooltip.label}</div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)', marginTop: 2 }}>
            {tooltip.status} · {tooltip.tasks} active task{tooltip.tasks !== 1 ? 's' : ''}
          </div>
        </div>
      )}
    </div>
  )
}

function StatChip({ value, label, accent, pulse }: { value: number; label: string; accent: string; pulse?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
      <span style={{
        fontFamily: 'var(--font-display, monospace)',
        fontWeight: 700,
        fontSize: 13,
        color: accent,
        ...(pulse ? { animation: 'hpulse 2s ease-in-out infinite' } : {}),
      }}>{value}</span>
      <span style={{ fontSize: 9.5, color: 'rgba(255,255,255,0.38)', letterSpacing: '0.02em' }}>{label}</span>
    </div>
  )
}
