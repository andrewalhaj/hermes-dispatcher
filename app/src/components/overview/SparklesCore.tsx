import { useEffect, useRef } from 'react'

interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  size: number
  phase: number
  phaseSpeed: number
}

interface SparklesCoreProps {
  particleColor?: string
  particleDensity?: number
  speed?: number
  minSize?: number
  maxSize?: number
  className?: string
}

export default function SparklesCore({
  particleColor = '#ffffff',
  particleDensity = 80,
  speed = 1,
  minSize = 0.6,
  maxSize = 1.4,
  className,
}: SparklesCoreProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Capture as definitely non-null so closures below don't lose narrowing
    const el: HTMLCanvasElement = canvas
    const cx: CanvasRenderingContext2D = ctx

    let rafId: number
    let particles: Particle[] = []
    let width = 0
    let height = 0

    function rand(min: number, max: number) {
      return min + Math.random() * (max - min)
    }

    function seed(w: number, h: number) {
      particles = Array.from({ length: particleDensity }, () => ({
        x: rand(0, w),
        y: rand(0, h),
        vx: rand(-0.4, 0.4) * speed,
        vy: rand(-0.4, 0.4) * speed,
        size: rand(minSize, maxSize),
        phase: rand(0, Math.PI * 2),
        phaseSpeed: rand(0.008, 0.025),
      }))
    }

    function resize() {
      const parent = el.parentElement
      if (!parent) return
      const newW = parent.clientWidth
      const newH = parent.clientHeight
      const significant = Math.abs(newW - width) > 20 || Math.abs(newH - height) > 20
      width = newW
      height = newH
      el.width = width
      el.height = height
      if (significant || particles.length === 0) {
        seed(width, height)
      }
    }

    function draw() {
      cx.clearRect(0, 0, width, height)
      for (const p of particles) {
        p.x += p.vx
        p.y += p.vy
        p.phase += p.phaseSpeed

        if (p.x < 0) p.x += width
        else if (p.x > width) p.x -= width
        if (p.y < 0) p.y += height
        else if (p.y > height) p.y -= height

        const opacity = 0.1 + 0.9 * (0.5 + 0.5 * Math.sin(p.phase))
        cx.beginPath()
        cx.arc(p.x, p.y, p.size, 0, Math.PI * 2)
        cx.fillStyle = particleColor
        cx.globalAlpha = opacity
        cx.fill()
      }
      cx.globalAlpha = 1
      rafId = requestAnimationFrame(draw)
    }

    resize()
    rafId = requestAnimationFrame(draw)

    const observer = new ResizeObserver(resize)
    const parent = el.parentElement
    if (parent) observer.observe(parent)

    return () => {
      cancelAnimationFrame(rafId)
      observer.disconnect()
    }
  }, [particleColor, particleDensity, speed, minSize, maxSize])

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none', zIndex: 0 }}
    />
  )
}
