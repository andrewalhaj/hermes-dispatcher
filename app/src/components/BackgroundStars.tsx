import { useEffect, useRef } from 'react'

interface Star {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  o: number
  phase: number
}

/** Fixed background starfield — subtle animated particles behind entire dashboard.
 *  Uses cool white/blue colors, very low opacity, slow drift. RAF-based with no
 *  expensive operations to maintain smooth 60fps. */
export default function BackgroundStars() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let stars: Star[] = []
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
          stars = []
          // ~160 stars spread across the background
          for (let i = 0; i < 160; i++) {
            stars.push({
              x: Math.random() * w,
              y: Math.random() * h,
              vx: (Math.random() - 0.5) * 0.08,
              vy: (Math.random() - 0.5) * 0.08,
              r: Math.random() * 1.1 + 0.3,
              o: Math.random() * 0.35 + 0.08,
              phase: Math.random() * Math.PI * 2,
            })
          }
          seeded = true
        }

        const t = performance.now() - start
        ctx.clearRect(0, 0, w, h)

        for (const s of stars) {
          // Slow drift — no attraction to a center, just steady movement
          s.x += s.vx
          s.y += s.vy

          // Wrap at edges instead of bouncing
          if (s.x < 0) s.x = w
          if (s.x > w) s.x = 0
          if (s.y < 0) s.y = h
          if (s.y > h) s.y = 0

          // Subtle twinkle: modulate opacity via sine wave
          const twinkle = 0.5 + 0.5 * Math.sin(s.phase + t / 1500)
          const o = Math.max(0.05, Math.min(0.47, s.o * twinkle))

          // Draw star: cool white or faint blue
          const color = Math.random() > 0.6 ? '#c8d8ff' : '#e8eeff'
          ctx.beginPath()
          ctx.arc(s.x, s.y, s.r, 0, 6.283)
          ctx.fillStyle = color
          ctx.globalAlpha = o
          ctx.fill()
        }

        ctx.globalAlpha = 1
      }

      raf = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      if (raf) cancelAnimationFrame(raf)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
        display: 'block',
      }}
    />
  )
}
