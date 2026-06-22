import { useEffect, useRef, useState } from 'react'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  o: number
  name: string
  tasks: number
}

interface TooltipState {
  x: number
  y: number
  name: string
  tasks: number
}

interface SwarmCanvasProps {
  accent: string
}

interface SwarmStats {
  agents: number
  connections: number
  active: number
}

const AGENT_NAMES = [
  'Orchestrator','Planner','Executor','Monitor','Router',
  'Analyzer','Dispatcher','Fetcher','Classifier','Summarizer',
  'Validator','Scheduler','Indexer','Synthesizer','Embedder',
  'Retriever','Encoder','Parser','Logger','Notifier',
  'Batcher','Merger','Splitter','Filter','Ranker',
  'Scorer','Tagger','Linker','Mapper','Resolver',
  'Crawler','Extractor','Formatter','Transformer','Reducer',
  'Aggregator','Publisher','Consumer','Producer','Relay',
  'Broker','Cache','Guard','Auditor','Tracer',
  'Inspector',
]

/** Animated particle swarm — drifting nodes attracted to a slowly orbiting center,
 *  linked by proximity lines. Cancels its RAF on unmount. */
export default function SwarmCanvas({ accent }: SwarmCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const particlesRef = useRef<Particle[]>([])
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const [stats, setStats] = useState<SwarmStats>({ agents: 0, connections: 0, active: 0 })
  const frameRef = useRef(0)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let seeded = false
    let raf = 0
    const start = performance.now()

    const draw = () => {
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      if (w >= 2 && h >= 2) {
        if (canvas.width !== w || canvas.height !== h) {
          canvas.width = w
          canvas.height = h
        }
        if (!seeded) {
          particlesRef.current = []
          for (let i = 0; i < 46; i++) {
            particlesRef.current.push({
              x: Math.random() * w,
              y: Math.random() * h,
              vx: (Math.random() - 0.5) * 0.6,
              vy: (Math.random() - 0.5) * 0.6,
              r: Math.random() * 1.6 + 0.8,
              o: Math.random() * 0.5 + 0.5,
              name: AGENT_NAMES[i % AGENT_NAMES.length],
              tasks: Math.floor(Math.random() * 8) + 1,
            })
          }
          seeded = true
        }

        const particles = particlesRef.current
        const t = performance.now() - start
        ctx.clearRect(0, 0, w, h)
        const cx = w / 2 + Math.sin(t / 2600) * w * 0.18
        const cy = h / 2 + Math.cos(t / 2600) * h * 0.18

        let activeCount = 0
        for (const p of particles) {
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
          if (sp > 0.32) activeCount++
          p.x += p.vx
          p.y += p.vy
          if (p.x < 0 || p.x > w) p.vx = -p.vx
          if (p.y < 0 || p.y > h) p.vy = -p.vy
          p.x = Math.max(0, Math.min(w, p.x))
          p.y = Math.max(0, Math.min(h, p.y))
          ctx.beginPath()
          ctx.arc(p.x, p.y, p.r, 0, 6.283)
          ctx.fillStyle = accent
          ctx.globalAlpha = p.o
          ctx.fill()
        }

        ctx.globalAlpha = 1
        ctx.lineWidth = 0.6
        ctx.strokeStyle = accent
        const CD = 88
        let connCount = 0
        for (let i = 0; i < particles.length; i++) {
          for (let j = i + 1; j < particles.length; j++) {
            const dx = particles[i].x - particles[j].x
            const dy = particles[i].y - particles[j].y
            const dist = Math.hypot(dx, dy)
            if (dist < CD) {
              connCount++
              ctx.globalAlpha = (1 - dist / CD) * 0.5
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
          setStats({ agents: particles.length, connections: connCount, active: activeCount })
        }
      }
      raf = requestAnimationFrame(draw)
    }

    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [accent])

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
        found = { x: mx, y: my, name: p.name, tasks: p.tasks }
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
      }}>
        <LegendRow icon={<DotIcon accent={accent} />} label="Each dot = an agent profile" />
        <LegendRow icon={<LineIcon accent={accent} />} label="Lines = cross-profile task links" />
        <LegendRow icon={<MoveIcon accent={accent} />} label="Movement = recent activity" />
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
        <StatChip value={stats.connections} label="connections" accent={accent} />
        <div style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.1)' }} />
        <StatChip value={stats.active} label="active" accent="#4ade80" pulse />
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
          <div style={{ fontSize: 11, fontWeight: 600, color: accent, letterSpacing: '0.01em' }}>{tooltip.name}</div>
          <div style={{ fontSize: 10, color: 'rgba(255,255,255,0.55)', marginTop: 2 }}>{tooltip.tasks} active task{tooltip.tasks !== 1 ? 's' : ''}</div>
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

function LegendRow({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
      {icon}
      <span style={{ fontSize: 10, color: 'rgba(255,255,255,0.45)', letterSpacing: '0.01em' }}>{label}</span>
    </div>
  )
}

function DotIcon({ accent }: { accent: string }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" style={{ flexShrink: 0 }}>
      <circle cx="5" cy="5" r="3" fill={accent} opacity={0.8} />
    </svg>
  )
}

function LineIcon({ accent }: { accent: string }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" style={{ flexShrink: 0 }}>
      <circle cx="1.5" cy="5" r="1.5" fill={accent} opacity={0.8} />
      <circle cx="8.5" cy="5" r="1.5" fill={accent} opacity={0.8} />
      <line x1="3" y1="5" x2="7" y2="5" stroke={accent} strokeWidth="0.8" opacity={0.5} />
    </svg>
  )
}

function MoveIcon({ accent }: { accent: string }) {
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" style={{ flexShrink: 0 }}>
      <circle cx="3" cy="5" r="1.5" fill={accent} opacity={0.8} />
      <path d="M5.5 5 L8.5 5 M7 3.5 L8.5 5 L7 6.5" stroke={accent} strokeWidth="0.8" fill="none" opacity={0.6} />
    </svg>
  )
}
