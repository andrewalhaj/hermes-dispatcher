import { useMemo } from 'react'

interface Layer {
  size: number
  count: number
  duration: string
  color: string
}

const LAYERS: Layer[] = [
  { size: 1, count: 560, duration: '90s',  color: 'rgba(255,255,255,0.65)' },
  { size: 2, count: 220, duration: '150s', color: 'rgba(255,255,255,0.45)' },
  { size: 3, count: 90,  duration: '220s', color: 'var(--ac, #f6b73c)' },
]

function genBoxShadow(count: number, color: string): string {
  const parts: string[] = []
  for (let i = 0; i < count; i++) {
    const x = Math.floor(Math.random() * 1600)
    const y = Math.floor(Math.random() * 2000)
    parts.push(`${x}px ${y}px 0 ${color}`)
  }
  return parts.join(', ')
}

export default function StarsBackground() {
  const shadows = useMemo(
    () => LAYERS.map((l) => genBoxShadow(l.count, l.color)),
    [],
  )

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        overflow: 'hidden',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    >
      {LAYERS.map((layer, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: 2000,
            animation: `hstars ${layer.duration} linear infinite`,
          }}
        >
          {/* Two copies offset by 2000px for seamless vertical loop */}
          <span
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: layer.size,
              height: layer.size,
              borderRadius: '50%',
              background: 'transparent',
              boxShadow: shadows[i],
            }}
          />
          <span
            style={{
              position: 'absolute',
              top: 2000,
              left: 0,
              width: layer.size,
              height: layer.size,
              borderRadius: '50%',
              background: 'transparent',
              boxShadow: shadows[i],
            }}
          />
        </div>
      ))}
    </div>
  )
}
