import { useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useSystemStats, type SysMetric, type SysDataPoint, type AgentMem } from './useSystemStats'

const cardLabelStyle: React.CSSProperties = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
  color: 'var(--text-faint)',
}

const SPIKE = '#fb6f6f'
/** Muted grey for unavailable / N/A states. */
const MUTED = '#6b7280'

/**
 * Per-metric accent colors. Keyed on the metric `key` from the hook so we
 * never touch the useSystemStats contract — the hook still supplies its own
 * `color`, we just override it visually here.
 */
const METRIC_COLORS: Record<string, string> = {
  cpu: '#60a5fa', // blue
  gpu: '#a78bfa', // violet
  vram: '#f472b6', // pink
  network: '#34d399', // emerald
  mem: '#fb923c', // orange (system memory section)
}

const accentFor = (key: string, unavailable: boolean): string =>
  unavailable ? MUTED : METRIC_COLORS[key] ?? MUTED

/** hex (#rrggbb) → rgba() string with the given alpha. */
const rgba = (hex: string, alpha: number): string => {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

const easeOutCubic = (t: number): number => 1 - Math.pow(1 - t, 3)

/**
 * CSS keyframes injected once. Glow pulses behind each icon (2s healthy,
 * 0.6s on spike); the header dot pulses as a status ring.
 */
const KEYFRAMES = `
@keyframes sysmon-glow-pulse {
  0%, 100% { opacity: 0.5; transform: scale(0.9); }
  50%      { opacity: 1;   transform: scale(1.1); }
}
@keyframes sysmon-dot-pulse {
  0%, 100% { opacity: 1;    transform: scale(1);    }
  50%      { opacity: 0.55; transform: scale(0.78); }
}
`

/**
 * 60fps numeric counter. Animates from the previous value toward `target`
 * via requestAnimationFrame easing (easeOutCubic) — CSS transitions lag on
 * React rerenders, so we drive the value imperatively.
 */
function useAnimatedNumber(target: number, duration = 300): number {
  const [display, setDisplay] = useState(target)
  const displayRef = useRef(target)
  const prevTarget = useRef(target)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    displayRef.current = display
  }, [display])

  useEffect(() => {
    if (target === prevTarget.current) return
    prevTarget.current = target
    const from = displayRef.current
    const delta = target - from
    const start = performance.now()

    const step = (now: number) => {
      const t = Math.min((now - start) / duration, 1)
      setDisplay(from + delta * easeOutCubic(t))
      if (t < 1) rafRef.current = requestAnimationFrame(step)
    }
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(step)

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [target, duration])

  return display
}

/**
 * Gauge semicircle arc (~40×24). Animates its stroke-dashoffset toward the
 * current value at 60fps via requestAnimationFrame (easeOutCubic, ~500ms).
 * Sits *above* the sparkline as the "value at a glance" visual.
 */
const AnimatedArc = ({
  value,
  max,
  color,
  width = 40,
  height = 24,
}: {
  value: number
  max: number
  color: string
  width?: number
  height?: number
}) => {
  const r = 16
  const cx = width / 2
  const cy = height - 2
  const arcLen = Math.PI * r
  const target = Math.max(0, Math.min(value / max, 1))

  const [frac, setFrac] = useState(target)
  const fracRef = useRef(target)
  const prevTarget = useRef(target)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    fracRef.current = frac
  }, [frac])

  useEffect(() => {
    if (target === prevTarget.current) return
    prevTarget.current = target
    const from = fracRef.current
    const delta = target - from
    const start = performance.now()

    const step = (now: number) => {
      const t = Math.min((now - start) / 500, 1)
      setFrac(from + delta * easeOutCubic(t))
      if (t < 1) rafRef.current = requestAnimationFrame(step)
    }
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(step)

    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current)
    }
  }, [target])

  const d = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`

  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden>
      <path d={d} fill="none" stroke={rgba(color, 0.14)} strokeWidth={4} strokeLinecap="round" />
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={4}
        strokeLinecap="round"
        strokeDasharray={arcLen}
        strokeDashoffset={arcLen * (1 - frac)}
        style={{ filter: `drop-shadow(0 0 2px ${rgba(color, 0.5)})` }}
      />
    </svg>
  )
}

/** Inline SVG icons (project has no lucide-react; keep zero new deps). */
const Icon = ({ name, color }: { name: string; color: string }) => {
  const common = {
    width: 15,
    height: 15,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: color,
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  switch (name) {
    case 'cpu':
      return (
        <svg {...common}>
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <rect x="9" y="9" width="6" height="6" />
          <path d="M9 1v3M15 1v3M9 20v3M15 20v3M1 9h3M1 15h3M20 9h3M20 15h3" />
        </svg>
      )
    case 'gpu':
      return (
        <svg {...common}>
          <path d="M13 2 3 14h7l-1 8 10-12h-7l1-8z" />
        </svg>
      )
    case 'vram':
      return (
        <svg {...common}>
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="M7 9h.01M7 13h.01" />
        </svg>
      )
    case 'network':
      return (
        <svg {...common}>
          <path d="M5 12.55a11 11 0 0 1 14 0M1.42 9a16 16 0 0 1 21 0M8.53 16.11a6 6 0 0 1 6.95 0" />
          <path d="M12 20h.01" />
        </svg>
      )
    case 'activity':
      return (
        <svg {...common}>
          <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
        </svg>
      )
    case 'monitor':
      return (
        <svg {...common}>
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8M12 17v4" />
        </svg>
      )
    default:
      return null
  }
}

/** Animated sparkline driven by raw points (spike-aware), viewBox W×H. */
const Sparkline = ({
  data,
  color,
  width = 60,
  height = 20,
  max = 100,
}: {
  data: SysDataPoint[]
  color: string
  width?: number
  height?: number
  max?: number
}) => {
  if (data.length < 2) {
    return <svg width={width} height={height} />
  }
  const points = data.map((point, index) => ({
    x: (index / (data.length - 1)) * width,
    y: height - (Math.min(point.value, max) / max) * height,
    isSpike: point.isSpike,
  }))
  const path = points.reduce(
    (acc, p, i) => (i === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`),
    '',
  )
  const hasSpikes = points.some((p) => p.isSpike)
  const gid = `sysgrad-${color.replace('#', '')}-${width}`

  return (
    <svg width={width} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={gid} x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor={hasSpikes ? SPIKE : color} stopOpacity={0.3} />
          <stop offset="100%" stopColor={hasSpikes ? SPIKE : color} stopOpacity={0.05} />
        </linearGradient>
      </defs>
      <motion.path
        d={`${path} L ${width} ${height} L 0 ${height} Z`}
        fill={`url(#${gid})`}
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.8, ease: 'easeOut' }}
      />
      <motion.path
        d={path}
        fill="none"
        stroke={hasSpikes ? SPIKE : color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.8, ease: 'easeOut' }}
      />
      {points.map((p, i) =>
        p.isSpike ? (
          <motion.circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={2}
            fill={SPIKE}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ delay: i * 0.04, type: 'spring', stiffness: 400, damping: 10 }}
          />
        ) : null,
      )}
    </svg>
  )
}

/** Soft radial glow that pulses behind an icon. Color = accent (red on spike). */
const IconGlow = ({ color, spike }: { color: string; spike: boolean }) => (
  <span
    aria-hidden
    style={{
      position: 'absolute',
      inset: 3,
      borderRadius: 8,
      color,
      background: `radial-gradient(circle, ${rgba(color, 0.28)} 0%, transparent 72%)`,
      animation: `sysmon-glow-pulse ${spike ? '0.6s' : '2s'} ease-in-out infinite`,
      willChange: 'transform, opacity',
      pointerEvents: 'none',
    }}
  />
)

const ResourceCard = ({ metric }: { metric: SysMetric }) => {
  const [isHovered, setIsHovered] = useState(false)
  const { hasSpike, unavailable } = metric
  const accent = accentFor(metric.key, unavailable)
  const glowColor = hasSpike ? SPIKE : accent
  const valColor = hasSpike ? SPIKE : '#e4e6ee'
  const animVal = useAnimatedNumber(metric.cur)
  const isNet = metric.unit === 'MB/s'
  const arcMax = isNet ? 60 : 100

  return (
    <motion.div
      className="flex items-center gap-2 p-1.5 rounded-lg"
      style={{
        background: `linear-gradient(135deg, ${rgba(accent, 0.07)} 0%, rgba(255,255,255,0.02) 100%)`,
        border: `1px solid ${rgba(accent, 0.15)}`,
      }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
    >
      <motion.div
        className="relative flex items-center justify-center rounded-md"
        style={{
          width: 28,
          height: 28,
          // backgroundColor is a paint property — drive it via a CSS transition
          // (not Framer's animate) so it never forces a compositor-incompatible tween.
          background: hasSpike ? 'rgba(251,111,111,0.14)' : rgba(accent, 0.06),
          transition: 'background 0.25s ease',
        }}
        animate={{
          scale: isHovered ? 1.1 : 1,
        }}
        transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      >
        {!unavailable && <IconGlow color={glowColor} spike={hasSpike} />}
        <span style={{ position: 'relative', zIndex: 1, display: 'inline-flex' }}>
          <Icon name={metric.key} color={hasSpike ? SPIKE : unavailable ? MUTED : accent} />
        </span>
      </motion.div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between" style={{ marginBottom: 2 }}>
          <span style={{ fontSize: 11, color: '#9298ab' }}>{metric.label}</span>
          <span className="mono" style={{ fontSize: 11.5, color: valColor }}>
            {unavailable ? 'N/A' : `${animVal.toFixed(isNet ? 1 : 0)} ${metric.unit}`}
          </span>
        </div>
        {unavailable ? (
          <div style={{ fontSize: 9.5, color: 'var(--text-faint)', paddingTop: 5, height: 44 }}>
            no device
          </div>
        ) : (
          <div className="flex flex-col" style={{ gap: 1 }}>
            <AnimatedArc value={metric.cur} max={arcMax} color={accent} />
            <Sparkline data={metric.data} color={accent} max={arcMax} />
          </div>
        )}
      </div>
    </motion.div>
  )
}

const AgentMemoryCard = ({ agent }: { agent: AgentMem }) => {
  const [isHovered, setIsHovered] = useState(false)
  return (
    <motion.div
      className="flex items-center gap-2 p-1.5 rounded-md"
      style={{
        // Hover tint via a CSS transition on background (paint property) instead
        // of Framer's whileHover backgroundColor, which can't run on the compositor.
        background: isHovered ? 'rgba(255,255,255,0.03)' : 'transparent',
        transition: 'background 0.2s ease',
      }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
    >
      <motion.div
        style={{ width: 8, height: 8, borderRadius: '50%', background: agent.color, flex: 'none' }}
        animate={{ scale: isHovered ? 1.25 : 1 }}
        transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between">
          <span style={{ fontSize: 12, color: '#c6cad8' }} className="truncate">
            {agent.name}
          </span>
          <span className="mono" style={{ fontSize: 11.5, color: '#e4e6ee', marginLeft: 8 }}>
            {agent.rss_mb}MB
          </span>
        </div>
        {agent.data.length > 1 && (
          <div style={{ marginTop: 2 }}>
            <Sparkline data={agent.data} color={agent.color} width={40} height={12} max={Math.max(...agent.data.map((d) => d.value), 1)} />
          </div>
        )}
      </div>
    </motion.div>
  )
}

/** Pulsing status dot for the tile header. */
const StatusDot = ({ state }: { state: 'healthy' | 'spike' | 'unreachable' }) => {
  const color = state === 'spike' ? SPIKE : state === 'unreachable' ? '#fbbf24' : '#4ade80'
  const animated = state !== 'unreachable'
  const speed = state === 'spike' ? '0.6s' : '2s'
  return (
    <span
      aria-hidden
      style={{
        width: 9,
        height: 9,
        borderRadius: '50%',
        background: color,
        color,
        display: 'inline-block',
        flex: 'none',
        willChange: animated ? 'transform, opacity' : 'auto',
        animation: animated ? `sysmon-dot-pulse ${speed} ease-out infinite` : 'none',
      }}
    />
  )
}

/** Machine selector dropdown (LH01 / LH02). Shared by collapsed + expanded headers. */
function MachineSelector({
  machine,
  menuOpen,
  setMenuOpen,
  onSelect,
}: {
  machine: 'mini' | 'studio'
  menuOpen: boolean
  setMenuOpen: (v: boolean) => void
  onSelect: (m: 'mini' | 'studio') => void
}) {
  return (
    <div className="relative" style={{ display: 'inline-flex' }}>
      <button
        onClick={(e) => {
          e.stopPropagation()
          setMenuOpen(!menuOpen)
        }}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 11,
          color: 'var(--text-muted)',
          background: 'rgba(255,255,255,0.05)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 6,
          padding: '3px 8px',
          cursor: 'pointer',
        }}
      >
        <Icon name="monitor" color="#9298ab" />
        {machine === 'studio' ? 'LH02' : 'LH01'}
        <motion.span
          animate={{ rotate: menuOpen ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          style={{ fontSize: 9, display: 'inline-block', lineHeight: 1 }}
        >
          ▾
        </motion.span>
      </button>
      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.96 }}
            transition={{ duration: 0.14 }}
            onClick={(e) => e.stopPropagation()}
            style={{
              position: 'absolute',
              top: '100%',
              right: 0,
              marginTop: 5,
              minWidth: 130,
              background: 'var(--s2, #1a1b22)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8,
              boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
              padding: 4,
              zIndex: 30,
            }}
          >
            {(['mini', 'studio'] as const).map((m) => (
              <button
                key={m}
                onClick={(e) => {
                  e.stopPropagation()
                  onSelect(m)
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 7,
                  width: '100%',
                  fontSize: 11.5,
                  textAlign: 'left',
                  color: machine === m ? '#e4e6ee' : '#9298ab',
                  background: machine === m ? 'rgba(255,255,255,0.06)' : 'transparent',
                  border: 'none',
                  borderRadius: 6,
                  padding: '6px 8px',
                  cursor: 'pointer',
                }}
              >
                <Icon name="monitor" color={machine === m ? '#e4e6ee' : '#9298ab'} />
                {m === 'studio' ? 'LH02' : 'LH01'}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/**
 * System Monitor tile — live CPU/GPU/VRAM/Network/Memory with spike detection,
 * framer-motion animations, and a collapsible per-agent memory breakdown.
 * Integrated as a panel tile (NOT a floating overlay). Polls /api/system @3s.
 */
export default function SystemMonitorTile() {
  const [machine, setMachine] = useState<'mini' | 'studio'>(
    () => (localStorage.getItem('sysmon_machine') as 'mini' | 'studio') ?? 'mini',
  )
  const [menuOpen, setMenuOpen] = useState(false)
  const sys = useSystemStats(machine)

  const selectMachine = (m: 'mini' | 'studio') => {
    setMachine(m)
    localStorage.setItem('sysmon_machine', m)
    setMenuOpen(false)
  }

  const dotState: 'healthy' | 'spike' | 'unreachable' = sys.unreachable
    ? 'unreachable'
    : sys.hasAnySpike
      ? 'spike'
      : 'healthy'

  const memAccent = METRIC_COLORS.mem
  const memAnim = useAnimatedNumber(sys.memPct)

  return (
    <div
      className="relative"
      style={{ background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 14, overflow: 'hidden', animation: 'hcellin 0.45s ease backwards', animationDelay: '0.28s' }}
    >
      <style>{KEYFRAMES}</style>
      <div style={{ padding: 18 }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
          <div className="inline-flex items-center" style={{ gap: 8 }}>
            <StatusDot state={dotState} />
            <span style={cardLabelStyle}>System Monitor</span>
            <AnimatePresence>
              {sys.unreachable ? (
                <motion.span
                  key="unreachable"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 14 }}
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: '#fbbf24',
                    background: 'rgba(251,191,36,0.12)',
                    border: '1px solid rgba(251,191,36,0.3)',
                    borderRadius: 5,
                    padding: '2px 6px',
                    lineHeight: 1,
                  }}
                >
                  unreachable
                </motion.span>
              ) : sys.hasAnySpike ? (
                <motion.span
                  key="spike"
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  exit={{ scale: 0, opacity: 0 }}
                  transition={{ type: 'spring', stiffness: 400, damping: 10 }}
                  style={{
                    fontSize: 10,
                    fontWeight: 600,
                    color: '#fff',
                    background: SPIKE,
                    borderRadius: 5,
                    padding: '2px 6px',
                    lineHeight: 1,
                  }}
                >
                  Spike
                </motion.span>
              ) : null}
            </AnimatePresence>
          </div>
          <div className="inline-flex items-center" style={{ gap: 10 }}>
            <MachineSelector
              machine={machine}
              menuOpen={menuOpen}
              setMenuOpen={setMenuOpen}
              onSelect={selectMachine}
            />
          </div>
        </div>

        <div className="sysmon-metric-grid">
          {sys.metrics.map((m) => (
            <ResourceCard key={m.key} metric={m} />
          ))}
        </div>
      </div>

      {/* System Memory — always visible, directly below the metric cards grid */}
      <div style={{ padding: '0 18px 18px' }}>
        <div
          className="flex items-center"
          style={{ paddingTop: 14, marginTop: 2, borderTop: '1px solid var(--border)', gap: 11 }}
        >
          <span
            className="relative inline-flex flex-none items-center justify-center"
            style={{ width: 32, height: 32, borderRadius: 9, background: rgba(memAccent, 0.12), border: `1px solid ${rgba(memAccent, 0.28)}` }}
          >
            <IconGlow color={memAccent} spike={false} />
            <span style={{ position: 'relative', zIndex: 1, display: 'inline-flex' }}>
              <Icon name="vram" color={memAccent} />
            </span>
          </span>
          <div className="flex-1" style={{ minWidth: 0 }}>
            <div className="flex items-center justify-between">
              <span style={{ fontSize: 12, color: '#c6cad8' }}>System Memory</span>
              <span className="mono" style={{ fontSize: 12, color: '#e4e6ee' }}>
                {sys.memUsedGb}/{sys.memTotalGb} GB · {memAnim.toFixed(0)}%
              </span>
            </div>
            <div style={{ marginTop: 2, height: 22 }}>
              <svg viewBox="0 0 100 22" preserveAspectRatio="none" style={{ width: '100%', height: 22, display: 'block' }}>
                {sys.memData.length > 1 && (
                  <SparkInline data={sys.memData} color={memAccent} />
                )}
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* Per-Agent Memory — always visible */}
      {sys.agents.length > 0 && (
        <div style={{ padding: '0 18px 18px' }}>
          <div style={{ marginTop: 2, paddingTop: 14, borderTop: '1px solid var(--border)' }}>
            <div style={{ ...cardLabelStyle, marginBottom: 9 }}>Per-Agent Memory</div>
            <div className="flex flex-col" style={{ gap: 2 }}>
              {sys.agents.map((agent, index) => (
                <motion.div
                  key={agent.name}
                  initial={{ x: -16, opacity: 0 }}
                  animate={{ x: 0, opacity: 1 }}
                  transition={{ delay: index * 0.08, type: 'spring', stiffness: 300, damping: 30 }}
                >
                  <AgentMemoryCard agent={agent} />
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/** Full-width memory sparkline using the same viewBox convention as the dashboard. */
const SparkInline = ({ data, color = SPIKE }: { data: SysDataPoint[]; color?: string }) => {
  const W = 100
  const H = 22
  const pts = data.map((p, i) => [
    (i / (data.length - 1)) * W,
    H - (Math.min(p.value, 100) / 100) * H,
  ])
  const line = 'M ' + pts.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' L ')
  const area = `${line} L ${W} ${H} L 0 ${H} Z`
  const hasSpike = data.some((d) => d.isSpike)
  const stroke = hasSpike ? SPIKE : color
  return (
    <>
      <path d={area} fill={`color-mix(in oklab, ${stroke} 18%, transparent)`} />
      <path
        d={line}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </>
  )
}
