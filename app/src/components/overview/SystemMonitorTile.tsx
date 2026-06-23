import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useSystemStats, type SysMetric, type SysDataPoint, type AgentMem } from './useSystemStats'

const cardLabelStyle: React.CSSProperties = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
  color: 'var(--text-faint)',
}

const SPIKE = '#fb6f6f'

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

const ResourceCard = ({ metric }: { metric: SysMetric }) => {
  const [isHovered, setIsHovered] = useState(false)
  const { hasSpike, unavailable } = metric
  const valColor = hasSpike ? SPIKE : '#e4e6ee'

  return (
    <motion.div
      className="flex items-center gap-2 p-1.5 rounded-lg"
      style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.05)' }}
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
    >
      <motion.div
        className="flex items-center justify-center rounded-md"
        style={{ width: 28, height: 28, background: 'rgba(255,255,255,0.04)' }}
        animate={{
          backgroundColor: hasSpike ? 'rgba(251,111,111,0.14)' : 'rgba(255,255,255,0.04)',
          scale: isHovered ? 1.1 : 1,
        }}
        transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      >
        <Icon name={metric.key} color={hasSpike ? SPIKE : '#9298ab'} />
      </motion.div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between" style={{ marginBottom: 2 }}>
          <span style={{ fontSize: 11, color: '#9298ab' }}>{metric.label}</span>
          <motion.span
            className="mono"
            style={{ fontSize: 11.5, color: valColor }}
            animate={{ color: valColor }}
          >
            {unavailable ? 'N/A' : `${metric.cur.toFixed(metric.unit === 'MB/s' ? 1 : 0)} ${metric.unit}`}
          </motion.span>
        </div>
        <div style={{ marginTop: 2, height: 20 }}>
          {unavailable ? (
            <div style={{ fontSize: 9.5, color: 'var(--text-faint)', paddingTop: 5 }}>no device</div>
          ) : (
            <Sparkline data={metric.data} color={metric.color} max={metric.unit === 'MB/s' ? 60 : 100} />
          )}
        </div>
      </div>
    </motion.div>
  )
}

const AgentMemoryCard = ({ agent }: { agent: AgentMem }) => {
  const [isHovered, setIsHovered] = useState(false)
  return (
    <motion.div
      className="flex items-center gap-2 p-1.5 rounded-md"
      onHoverStart={() => setIsHovered(true)}
      onHoverEnd={() => setIsHovered(false)}
      transition={{ type: 'spring', stiffness: 400, damping: 25 }}
      whileHover={{ backgroundColor: 'rgba(255,255,255,0.03)' }}
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

/**
 * System Monitor tile — live CPU/GPU/VRAM/Network/Memory with spike detection,
 * framer-motion animations, and a collapsible per-agent memory breakdown.
 * Integrated as a panel tile (NOT a floating overlay). Polls /api/system @3s.
 */
export default function SystemMonitorTile() {
  const sys = useSystemStats()
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div
      className="relative"
      style={{ background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 14, overflow: 'hidden' }}
    >
      <motion.div
        className="cursor-pointer"
        style={{ padding: 18 }}
        onClick={() => setIsExpanded((v) => !v)}
        whileHover={{ backgroundColor: 'rgba(255,255,255,0.015)' }}
        transition={{ duration: 0.2 }}
      >
        <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
          <div className="inline-flex items-center" style={{ gap: 8 }}>
            <motion.div
              animate={{ rotate: sys.hasAnySpike ? 360 : 0 }}
              transition={{ duration: 0.5, ease: 'easeInOut' }}
              style={{ display: 'inline-flex' }}
            >
              <Icon name="activity" color={sys.hasAnySpike ? SPIKE : '#4ade80'} />
            </motion.div>
            <span style={cardLabelStyle}>System Monitor</span>
            <AnimatePresence>
              {sys.hasAnySpike && (
                <motion.span
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
              )}
            </AnimatePresence>
          </div>
          <div className="inline-flex items-center" style={{ gap: 10 }}>
            <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{sys.hostLabel}</span>
            <motion.span
              animate={{ rotate: isExpanded ? 180 : 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              style={{ color: 'var(--text-faint)', fontSize: 10, display: 'inline-block' }}
            >
              ▼
            </motion.span>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {sys.metrics.map((m) => (
            <ResourceCard key={m.key} metric={m} />
          ))}
        </div>
      </motion.div>

      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            style={{ overflow: 'hidden' }}
          >
            <div style={{ padding: '0 18px 18px' }}>
              {/* System Memory */}
              <div
                className="flex items-center"
                style={{ paddingTop: 14, marginTop: 2, borderTop: '1px solid var(--border)', gap: 11 }}
              >
                <span
                  className="inline-flex flex-none items-center justify-center"
                  style={{ width: 32, height: 32, borderRadius: 9, background: 'rgba(251,111,111,0.12)', border: '1px solid rgba(251,111,111,0.28)' }}
                >
                  <Icon name="vram" color={SPIKE} />
                </span>
                <div className="flex-1" style={{ minWidth: 0 }}>
                  <div className="flex items-center justify-between">
                    <span style={{ fontSize: 12, color: '#c6cad8' }}>System Memory</span>
                    <span className="mono" style={{ fontSize: 12, color: '#e4e6ee' }}>
                      {sys.memUsedGb}/{sys.memTotalGb} GB · {sys.memPct.toFixed(0)}%
                    </span>
                  </div>
                  <div style={{ marginTop: 2, height: 22 }}>
                    <svg viewBox="0 0 100 22" preserveAspectRatio="none" style={{ width: '100%', height: 22, display: 'block' }}>
                      {sys.memData.length > 1 && (
                        <SparkInline data={sys.memData} />
                      )}
                    </svg>
                  </div>
                </div>
              </div>

              {/* Per-agent memory */}
              {sys.agents.length > 0 && (
                <div style={{ marginTop: 14 }}>
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
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** Full-width memory sparkline using the same viewBox convention as the dashboard. */
const SparkInline = ({ data }: { data: SysDataPoint[] }) => {
  const W = 100
  const H = 22
  const pts = data.map((p, i) => [
    (i / (data.length - 1)) * W,
    H - (Math.min(p.value, 100) / 100) * H,
  ])
  const line = 'M ' + pts.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' L ')
  const area = `${line} L ${W} ${H} L 0 ${H} Z`
  const hasSpike = data.some((d) => d.isSpike)
  const stroke = hasSpike ? SPIKE : '#fb6f6f'
  return (
    <>
      <path d={area} fill="color-mix(in oklab, #fb6f6f 18%, transparent)" />
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
