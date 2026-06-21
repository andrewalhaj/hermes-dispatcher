import { useEffect, useRef } from 'react'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  r: number
  o: number
}

interface SwarmCanvasProps {
  accent: string
}

/** Animated particle swarm — drifting nodes attracted to a slowly orbiting center,
 *  linked by proximity lines. Cancels its RAF on unmount. */
export default function SwarmCanvas({ accent }: SwarmCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let particles: Particle[] = []
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
          particles = []
          for (let i = 0; i < 46; i++) {
            particles.push({
              x: Math.random() * w,
              y: Math.random() * h,
              vx: (Math.random() - 0.5) * 0.6,
              vy: (Math.random() - 0.5) * 0.6,
              r: Math.random() * 1.6 + 0.8,
              o: Math.random() * 0.5 + 0.5,
            })
          }
          seeded = true
        }

        const t = performance.now() - start
        ctx.clearRect(0, 0, w, h)
        const cx = w / 2 + Math.sin(t / 2600) * w * 0.18
        const cy = h / 2 + Math.cos(t / 2600) * h * 0.18

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
        for (let i = 0; i < particles.length; i++) {
          for (let j = i + 1; j < particles.length; j++) {
            const dx = particles[i].x - particles[j].x
            const dy = particles[i].y - particles[j].y
            const dist = Math.hypot(dx, dy)
            if (dist < CD) {
              ctx.globalAlpha = (1 - dist / CD) * 0.5
              ctx.beginPath()
              ctx.moveTo(particles[i].x, particles[i].y)
              ctx.lineTo(particles[j].x, particles[j].y)
              ctx.stroke()
            }
          }
        }
        ctx.globalAlpha = 1
      }
      raf = requestAnimationFrame(draw)
    }

    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [accent])

  return <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block', zIndex: 0 }} />
}
