import { useState } from 'react'
import type { StatTileData } from '../../data/overview'
import { PathIcon } from '../icons'

interface StatTileProps {
  stat: StatTileData
  onClick?: () => void
}

export default function StatTile({ stat, onClick }: StatTileProps) {
  const [hover, setHover] = useState(false)
  // Glow position within the tile; starts at the data-driven resting point.
  const [glow, setGlow] = useState<{ x: string; y: string }>({ x: stat.glowX, y: stat.glowY })

  return (
    <div
      onClick={onClick}
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect()
        setGlow({ x: `${e.clientX - r.left}px`, y: `${e.clientY - r.top}px` })
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className="relative cursor-pointer overflow-hidden"
      style={{
        background: 'var(--s3)',
        border: '1px solid var(--tile-border)',
        borderRadius: 13,
        padding: '18px 20px',
        transform: hover ? 'translateY(-3px)' : 'none',
        borderColor: hover ? 'var(--tile-border-hover)' : 'var(--tile-border)',
        boxShadow: hover ? '0 12px 30px rgba(0,0,0,0.42)' : 'none',
        transition: 'transform 0.25s, border-color 0.25s, box-shadow 0.25s',
      }}
    >
      <span style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 2, background: stat.accent }} />
      {/* corner wash on hover */}
      <span
        style={{
          position: 'absolute',
          inset: 0,
          pointerEvents: 'none',
          opacity: hover ? 1 : 0,
          transition: 'opacity 0.3s',
          background: `linear-gradient(135deg, color-mix(in oklab, ${stat.accent} 20%, transparent), transparent 68%)`,
        }}
      />
      {/* cursor-tracking glow */}
      <span
        style={{
          position: 'absolute',
          left: glow.x,
          top: glow.y,
          width: 150,
          height: 150,
          borderRadius: '50%',
          transform: 'translate(-50%, -50%)',
          pointerEvents: 'none',
          filter: 'blur(12px)',
          mixBlendMode: 'screen',
          opacity: hover ? 1 : 0,
          transition: 'opacity 0.3s',
          background: `radial-gradient(circle, color-mix(in oklab, ${stat.accent} 85%, transparent) 0%, color-mix(in oklab, ${stat.accent} 38%, transparent) 28%, color-mix(in oklab, ${stat.accent} 12%, transparent) 50%, transparent 68%)`,
        }}
      />
      <span
        className="relative inline-flex items-center justify-center"
        style={{
          width: 34,
          height: 34,
          borderRadius: 10,
          background: `color-mix(in oklab, ${stat.accent} 14%, transparent)`,
          border: `1px solid color-mix(in oklab, ${stat.accent} 30%, transparent)`,
          color: stat.accent,
          marginBottom: 14,
        }}
      >
        <PathIcon d={stat.iconPath} />
      </span>
      <div style={{ position: 'relative', fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 34, lineHeight: 1, letterSpacing: '-0.01em', color: 'var(--text-primary)' }}>
        {stat.value}
      </div>
      <div style={{ position: 'relative', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-faint)', marginTop: 8 }}>
        {stat.label}
      </div>
      <div style={{ position: 'relative', height: 18, marginTop: 10, overflow: 'hidden' }}>
        <span
          className="inline-flex items-center"
          style={{
            gap: 5,
            fontSize: 12,
            color: stat.accent,
            opacity: hover ? 1 : 0,
            transform: hover ? 'translateY(0)' : 'translateY(8px)',
            transition: 'opacity 0.28s, transform 0.28s',
          }}
        >
          {stat.sub}
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path d="M9 6l6 6-6 6" />
          </svg>
        </span>
      </div>
    </div>
  )
}
