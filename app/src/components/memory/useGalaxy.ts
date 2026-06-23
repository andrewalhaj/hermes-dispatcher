import { useEffect, useRef } from 'react'
import type { GalaxyData, MemNode } from '../../data/phase3'

interface UseGalaxyOpts {
  data: GalaxyData
  paused: boolean
  selectedId: string | null
  onSelect: (node: MemNode) => void
}

// Fibonacci sphere — evenly distributes N points on a sphere surface
function fibSphere(i: number, total: number, radius: number): [number, number, number] {
  const phi = Math.acos(1 - 2 * (i + 0.5) / total)
  const theta = Math.PI * (1 + Math.sqrt(5)) * i
  return [
    radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.sin(phi) * Math.sin(theta),
    radius * Math.cos(phi),
  ]
}

const lerp = (a: number, b: number, t: number) => a + (b - a) * t

// smoothstep — eased 0→1 ramp between edge0 and edge1
function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.max(0, Math.min(1, (x - edge0) / (edge1 - edge0)))
  return t * t * (3 - 2 * t)
}

/** Imperative 3D galaxy renderer on a <canvas>. Pure math projection — no
 *  Three.js. Mirrors the prototype's drawGalaxy/attachGalaxy logic.
 *  - auto-orbit yaw +0.0006/frame when not dragging and not paused
 *  - drag to rotate, scroll to zoom
 *  - hover highlights + labels, click selects a node */
export function useGalaxy({ data, paused, selectedId, onSelect }: UseGalaxyOpts) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  // Live refs so the RAF loop always reads current values without re-binding.
  const pausedRef = useRef(paused)
  const selRef = useRef(selectedId)
  const onSelRef = useRef(onSelect)
  useEffect(() => { pausedRef.current = paused }, [paused])
  useEffect(() => { selRef.current = selectedId }, [selectedId])
  useEffect(() => { onSelRef.current = onSelect }, [onSelect])

  useEffect(() => {
    const c = canvasRef.current
    if (!c) return
    const ctx = c.getContext('2d')
    if (!ctx) return

    const view = { yaw: 0, pitch: 0, zoom: 1, drag: false, hover: -1, mx: null as number | null, my: null as number | null }
    let px = 0, py = 0
    // Per-node positions: spherePos = Fibonacci sphere (zoomed out), clusterPos = original scatter (zoomed in).
    const total = data.nodes.length
    const spherePos: [number, number, number][] = data.nodes.map((_, i) => fibSphere(i, total, 2.2))
    const clusterPos: [number, number, number][] = data.nodes.map((m) => [m.x, m.y, m.z])
    const proj: ({ i: number; sx: number; sy: number; z2: number; s: number; m: MemNode; depth: number } | null)[] = new Array(data.nodes.length).fill(null)

    const onDown = (e: MouseEvent) => { view.drag = true; px = e.clientX; py = e.clientY; c.style.cursor = 'grabbing' }
    const onUp = () => { if (view.drag) { view.drag = false; c.style.cursor = 'grab' } }
    const onMove = (e: MouseEvent) => {
      const r = c.getBoundingClientRect()
      view.mx = e.clientX - r.left
      view.my = e.clientY - r.top
      if (view.drag) {
        view.yaw += (e.clientX - px) * 0.008
        view.pitch += (e.clientY - py) * 0.008
        view.pitch = Math.max(-1.4, Math.min(1.4, view.pitch))
        px = e.clientX
        py = e.clientY
      }
    }
    const onLeave = () => { view.mx = null; view.my = null }
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      view.zoom = Math.max(0.45, Math.min(3, view.zoom * (e.deltaY < 0 ? 1.08 : 0.92)))
    }
    const onClick = () => { if (view.hover >= 0 && data.nodes[view.hover]) onSelRef.current(data.nodes[view.hover]) }

    c.addEventListener('mousedown', onDown)
    window.addEventListener('mouseup', onUp)
    c.addEventListener('mousemove', onMove)
    c.addEventListener('mouseleave', onLeave)
    c.addEventListener('wheel', onWheel, { passive: false })
    c.addEventListener('click', onClick)

    let raf = 0
    const draw = () => {
      const w = c.clientWidth, h = c.clientHeight
      if (w < 2 || h < 2) { raf = requestAnimationFrame(draw); return }
      const dpr = Math.min(window.devicePixelRatio || 1, 3)
      if (c.width !== Math.floor(w * dpr) || c.height !== Math.floor(h * dpr)) {
        c.width = Math.floor(w * dpr)
        c.height = Math.floor(h * dpr)
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      }
      if (!view.drag && !pausedRef.current) view.yaw += 0.0006
      const cx = w / 2, cy = h / 2, focal = 4.6, baseScale = Math.min(w, h) * 0.2 * view.zoom
      const cosY = Math.cos(view.yaw), sinY = Math.sin(view.yaw), cosP = Math.cos(view.pitch), sinP = Math.sin(view.pitch)
      proj.fill(null)
      const pts: NonNullable<(typeof proj)[number]>[] = []
      // t: 0 = full sphere (zoomed out), 1 = full cluster (zoomed in)
      const t = smoothstep(0.6, 1.5, view.zoom)
      for (let i = 0; i < data.nodes.length; i++) {
        const m = data.nodes[i]
        const sp = spherePos[i], cp = clusterPos[i]
        const nx0 = lerp(sp[0], cp[0], t), ny0 = lerp(sp[1], cp[1], t), nz0 = lerp(sp[2], cp[2], t)
        const x1 = nx0 * cosY - nz0 * sinY, z1 = nx0 * sinY + nz0 * cosY
        const y1 = ny0 * cosP - z1 * sinP, z2 = ny0 * sinP + z1 * cosP
        const denom = focal - z2
        if (denom <= 0.3) continue
        const s = focal / denom
        const o = { i, sx: cx + x1 * s * baseScale, sy: cy + y1 * s * baseScale, z2, s, m, depth: Math.max(0.12, Math.min(1, (z2 + 3.2) / 6.4)) }
        proj[i] = o
        pts.push(o)
      }
      pts.sort((a, b) => a.z2 - b.z2)
      // hover pick
      let hover = -1, best = 13
      if (view.mx != null && !view.drag) {
        for (const p of pts) {
          const r = Math.max(4, p.m.importance * 9 * p.s)
          const d = Math.hypot(p.sx - view.mx, p.sy - (view.my ?? 0))
          if (d < r + 5 && d < best) { best = d; hover = p.i }
        }
      }
      view.hover = hover

      ctx.clearRect(0, 0, w, h)
      // nebula wash
      const neb = ctx.createRadialGradient(cx, cy * 0.9, 0, cx, cy, Math.max(w, h) * 0.62)
      neb.addColorStop(0, 'rgba(124,110,205,0.11)')
      neb.addColorStop(0.5, 'rgba(88,78,158,0.05)')
      neb.addColorStop(1, 'transparent')
      ctx.fillStyle = neb
      ctx.fillRect(0, 0, w, h)
      // edges
      ctx.lineWidth = 0.6
      for (const lk of data.links) {
        const pa = proj[lk[0]], pb = proj[lk[1]]
        if (!pa || !pb) continue
        const hl = view.hover === lk[0] || view.hover === lk[1]
        const al = 0.06 + 0.14 * Math.min(pa.depth, pb.depth)
        ctx.strokeStyle = hl ? 'rgba(205,205,255,0.6)' : `rgba(158,158,222,${al.toFixed(3)})`
        ctx.beginPath()
        ctx.moveTo(pa.sx, pa.sy)
        ctx.lineTo(pb.sx, pb.sy)
        ctx.stroke()
      }
      // nodes
      const sel = selRef.current
      for (const p of pts) {
        const depth = p.depth
        const r = Math.max(1.4, p.m.importance * 8.5 * p.s)
        const col = p.m.color
        const isH = p.i === view.hover
        const isS = sel != null && sel === p.m.id
        const a = 0.3 + 0.6 * depth
        const g = ctx.createRadialGradient(p.sx, p.sy, 0, p.sx, p.sy, r * 3.6)
        g.addColorStop(0, '#ffffff')
        g.addColorStop(0.28, col + 'dd')
        g.addColorStop(0.62, col + '40')
        g.addColorStop(1, 'transparent')
        ctx.globalAlpha = a * (isH || isS ? 1 : 0.7)
        ctx.fillStyle = g
        ctx.beginPath()
        ctx.arc(p.sx, p.sy, r * 3.6, 0, 6.283)
        ctx.fill()
        ctx.globalAlpha = Math.min(1, a + 0.25)
        ctx.fillStyle = '#fff'
        ctx.beginPath()
        ctx.arc(p.sx, p.sy, Math.max(1, r * 0.6), 0, 6.283)
        ctx.fill()
        if (isH || isS) {
          ctx.globalAlpha = 1
          ctx.strokeStyle = col
          ctx.lineWidth = 1.5
          ctx.beginPath()
          ctx.arc(p.sx, p.sy, r + 6, 0, 6.283)
          ctx.stroke()
        }
      }
      // labels
      ctx.font = '11px Inter, sans-serif'
      ctx.textBaseline = 'middle'
      for (const p of pts) {
        if (!p.m.label || p.depth < 0.42) continue
        const r = Math.max(2, p.m.importance * 8.5 * p.s)
        ctx.globalAlpha = Math.min(0.92, 0.4 + p.depth * 0.6)
        ctx.fillStyle = 'rgba(232,232,242,0.95)'
        ctx.fillText(p.m.title, p.sx + r + 7, p.sy)
      }
      if (view.hover >= 0) {
        const p = proj[view.hover]
        if (p && !p.m.label) {
          const r = Math.max(2, p.m.importance * 8.5 * p.s)
          ctx.globalAlpha = 1
          ctx.fillStyle = '#fff'
          ctx.fillText(p.m.title, p.sx + r + 7, p.sy)
        }
      }
      ctx.globalAlpha = 1
      c.style.cursor = hover >= 0 ? 'pointer' : view.drag ? 'grabbing' : 'grab'
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(raf)
      c.removeEventListener('mousedown', onDown)
      window.removeEventListener('mouseup', onUp)
      c.removeEventListener('mousemove', onMove)
      c.removeEventListener('mouseleave', onLeave)
      c.removeEventListener('wheel', onWheel)
      c.removeEventListener('click', onClick)
    }
  }, [data])

  return canvasRef
}
