import { useEffect, useRef, useState } from 'react'

interface Agent {
  name: string
  tasks: number
  status: 'running' | 'idle'
  color: string
}

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  o: number
  name: string
  tasks: number
  status: 'running' | 'idle'
  color: string
}

interface TooltipState {
  x: number
  y: number
  name: string
  tasks: number
  status: 'running' | 'idle'
}

interface SwarmCanvasProps {
  accent: string
}

interface SwarmStats {
  agents: number
  running: number
  tasks: number
}

/** Shape of a task row from GET /api/kanban/tasks. */
interface KanbanTask {
  assignee: string | null
  status: string
}

// Deterministic per-agent colors so they don't change on re-render.
const AGENT_COLORS: Record<string, string> = {
  coder: '#5aa2f0', // blue
  'coder-b': '#2dd4bf', // teal
  'ha-bot': '#4ade80', // green
  default: '#f6b73c', // amber (accent)
  executor: '#f59e0b', // yellow
  'swarm-synthesizer': '#9b8cff', // purple
  'swarm-verifier': '#a78bfa',
}

const FALLBACK_COLORS = ['#fb923c', '#e879f9', '#38bdf8', '#a3e635', '#f472b6']

/** Stable hash → fallback color for agents not in the explicit palette. */
function colorForAgent(name: string): string {
  if (AGENT_COLORS[name]) return AGENT_COLORS[name]
  let h = 0
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) | 0
  }
  return FALLBACK_COLORS[Math.abs(h) % FALLBACK_COLORS.length]
}

/** Reduce live kanban tasks to a per-agent agent list. */
function tasksToAgents(tasks: KanbanTask[]): Agent[] {
  const byAgent = new Map<string, { active: number; running: number }>()
  for (const t of tasks) {
    if (!t.assignee) continue
    // Only surface agents with active work — skip done/archived/completed tasks
    if (t.status === 'done' || t.status === 'archived') continue
    const entry = byAgent.get(t.assignee) ?? { active: 0, running: 0 }
    if (t.status === 'running' || t.status === 'ready') entry.active++
    if (t.status === 'running') entry.running++
    byAgent.set(t.assignee, entry)
  }
  return Array.from(byAgent.entries())
    .map(([name, e]) => ({
      name,
      tasks: e.active,
      status: (e.running > 0 ? 'running' : 'idle') as 'running' | 'idle',
      color: colorForAgent(name),
    }))
    .sort((a, b) => b.tasks - a.tasks || a.name.localeCompare(b.name))
}

/** Animated particle swarm — drifting nodes attracted to a slowly orbiting center,
 *  linked by proximity lines. Each particle is a real agent, colored by profile and
 *  sized by active task count. Live data polls every 10s; canvas draws at 60fps. */
export default function SwarmCanvas({ accent }: SwarmCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const agentsRef = useRef<Agent[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [stats, setStats] = useState<SwarmStats>({ agents: 0, running: 0, tasks: 0 })
  const frameRef = useRef(0)

  // Poll live agent data every 10s (NOT on every draw frame).
  useEffect(() => {
    let cancelled = false

    const load = () => {
      fetch('/api/kanban/tasks')
        .then((r) => r.json())
        .then((data: KanbanTask[]) => {
          if (cancelled || !Array.isArray(data)) return
          const next = tasksToAgents(data)
          agentsRef.current = next
          setAgents(next)
        })
        .catch(() => {/* server not up yet — keep last known agents */})
    }

    load()
    const id = window.setInterval(load, 10_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let raf = 0
    const start = performance.now()
    let lastSig = ''

    /** Particle radius scales with active task count so busier agents are bigger. */
    const radiusFor = (tasks: number) => 1.5 + Math.min(tasks, 10) * 0.25

    /** (Re)seed particles when the agent set changes; preserve positions of agents
     *  that persist so the swarm doesn't visually reshuffle on every poll. */
    const reconcile = (w: number, h: number) => {
      const agentList = agentsRef.current
      const sig = agentList.map((a) => `${a.name}:${a.tasks}:${a.status}`).join('|')
      if (sig === lastSig) return
      lastSig = sig

      const existing = new Map(particlesRef.current.map((p) => [p.name, p]))
      const next: Particle[] = agentList.map((a) => {
        const prev = existing.get(a.name)
        if (prev) {
          prev.tasks = a.tasks
          prev.status = a.status
          prev.color = a.color
          prev.r = radiusFor(a.tasks)
          prev.o = a.status === 'running' ? 0.9 : 0.4
          return prev
        }
        return {
          x: Math.random() * w,
          y: Math.random() * h,
          vx: (Math.random() - 0.5) * 0.6,
          vy: (Math.random() - 0.5) * 0.6,
          r: radiusFor(a.tasks),
          o: a.status === 'running' ? 0.9 : 0.4,
          name: a.name,
          tasks: a.tasks,
          status: a.status,
          color: a.color,
        }
      })
      particlesRef.current = next
    }

    const draw = () => {
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      if (w >= 2 && h >= 2) {
        // HiDPI/Retina: back the canvas with devicePixelRatio physical pixels,
        // then scale the 2D context so all drawing coords stay in CSS pixels.
        const dpr = window.devicePixelRatio || 1
        const pw = Math.round(w * dpr)
        const ph = Math.round(h * dpr)
        if (canvas.width !== pw || canvas.height !== ph) {
          canvas.width = pw
          canvas.height = ph
        }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

        reconcile(w, h)

        const particles = particlesRef.current
        const t = performance.now() - start
        ctx.clearRect(0, 0, w, h)
        const cx = w / 2 + Math.sin(t / 2600) * w * 0.18
        const cy = h / 2 + Math.cos(t / 2600) * h * 0.18

        let runningCount = 0
        for (const p of particles) {
          if (p.status === 'running') runningCount++
          const dx = cx - p.x
          const dy = cy - p.y
          const d = Math.hypot(dx, dy) || 1
          if (d > 55) {
            p.vx += (dx / d) * 0.012
            p.vy += (dy / d) * 0.012
          }
          if (Math.random() > 0.97) {
            p.vx += (Math.random() - 0.5) * 0.15
            p.vy += (Math.random() - 0.5) * 0.15
          }
          const sp = Math.hypot(p.vx, p.vy)
          const mx = 0.9
          if (sp > mx) {
            p.vx *= mx / sp
            p.vy *= mx / sp
          }
          p.x += p.vx
          p.y += p.vy
          if (p.x < 0 || p.x > w) p.vx = -p.vx
          if (p.y < 0 || p.y > h) p.vy = -p.vy
          p.x = Math.max(0, Math.min(w, p.x))
          p.y = Math.max(0, Math.min(h, p.y))
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.r, 0, 6.283)
          ctx.fillStyle = p.color
          ctx.globalAlpha = p.o
          ctx.fill()
        }

        // Connection lines between nearby agents — neutral blend so colors don't clash.
        ctx.globalAlpha = 1
        ctx.lineWidth = 0.6
        const CD = 88
        let connCount = 0
        for (let i = 0; i < particles.length; i++) {
          for (let j = i + 1; j < particles.length; j++) {
            const dx = particles[i].x - particles[j].x
            const dy = particles[i].y - particles[j].y
            const dist = Math.hypot(dx, dy)
            if (dist < CD) {
              connCount++
              const fade = (1 - dist / CD) * 0.15
              ctx.strokeStyle = `rgba(255,255,255,${fade.toFixed(3)})`
              ctx.beginPath()
              ctx.moveTo(particles[i].x, particles[i].y)
              ctx.lineTo(particles[j].x, particles[j].y)
              ctx.stroke()
            }
          }
        }
        ctx.globalAlpha = 1

        frameRef.current++
        if (frameRef.current % 20 === 0) {
          const totalTasks = particles.reduce((acc, p) => acc + p.tasks, 0)
          setStats({ agents: particles.length, running: runningCount, tasks: totalTasks })
        }
        void connCount
      }
      raf = requestAnimationFrame(draw)
    }

    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [])

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return
    const rect = canvas.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const HIT = 12

    let found: TooltipState | null = null
    for (const p of particlesRef.current) {
      if (Math.hypot(p.x - mx, p.y - my) < HIT) {
        found = { x: mx, y: my, name: p.name, tasks: p.tasks, status: p.status }
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

      {/* Legend — bottom-left: real agent names + colored dots */}
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
        {agents.length === 0 ? (
          <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.4)' }}>No active agents</span>
        ) : (
          agents.slice(0, 8).map((a) => (
            <div key={a.name} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <svg width="10" height="10" viewBox="0 0 10 10" style={{ flexShrink: 0 }}>
                <circle cx="5" cy="5" r="3" fill={a.color} opacity={a.status === 'running' ? 0.95 : 0.45} />
              </svg>
              <span style={{
                fontSize: 10,
                color: a.status === 'running' ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.4)',
                letterSpacing: '0.01em',
              }}>{a.name}</span>
              <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.32)', marginLeft: 'auto', paddingLeft: 8 }}>
                {a.tasks}
              </span>
            </div>
          ))
        )}
      </div>

      {/* Stats overlay — top-right: real counts */}
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

      {/* Hover tooltip — real agent name, status, task count */}
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
          <div style={{ fontSize: 11, fontWeight: 600, color: accent, letterSpacing: '0.01em' }}>{tooltip.name}</div>
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
