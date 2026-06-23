import { useEffect, useRef } from 'react'
import * as THREE from 'three'

// ---------------------------------------------------------------------------
// Aurora shader (layer 2 — sits above the star dots, below the UI)
// ---------------------------------------------------------------------------
const VERT = `void main() { gl_Position = vec4(position, 1.0); }`

const FRAG = `
uniform float iTime;
uniform vec2 iResolution;
#define NUM_OCTAVES 3
float rand(vec2 n) { return fract(sin(dot(n, vec2(12.9898, 4.1414))) * 43758.5453); }
float noise(vec2 p) {
  vec2 ip = floor(p); vec2 u = fract(p);
  u = u * u * (3.0 - 2.0 * u);
  return mix(mix(rand(ip), rand(ip+vec2(1,0)), u.x), mix(rand(ip+vec2(0,1)), rand(ip+vec2(1,1)), u.x), u.y) * u.y;
}
float fbm(vec2 x) {
  float v=0.0, a=0.3; vec2 shift=vec2(100.0);
  mat2 rot=mat2(cos(0.5),sin(0.5),-sin(0.5),cos(0.5));
  for(int i=0;i<NUM_OCTAVES;++i){v+=a*noise(x);x=rot*x*2.0+shift;a*=0.4;}
  return v;
}
void main() {
  vec2 shake = vec2(sin(iTime*1.2)*0.004, cos(iTime*2.1)*0.004);
  // Wider transform so streaks span the full viewport
  vec2 p = ((gl_FragCoord.xy + shake*iResolution.xy) - iResolution.xy*0.5)
           / iResolution.y * mat2(4.5,-3.0,3.0,4.5);
  vec2 v; vec4 o = vec4(0.0);
  float f = 2.0 + fbm(p + vec2(iTime*4.0,0.0))*0.5;
  // 20 streaks — lighter on Intel UHD 630, each contributes a bit more
  for(float i=0.0;i<20.0;i++){
    v = p + cos(i*i+(iTime+p.x*0.06)*0.02+i*vec2(13.0,11.0))*4.5
        + vec2(sin(iTime*2.5+i)*0.004, cos(iTime*3.0-i)*0.004);
    float tailNoise = fbm(v+vec2(iTime*0.4,i))*0.25*(1.0-(i/20.0));
    vec4 col = vec4(0.1+0.3*sin(i*0.2+iTime*0.4), 0.3+0.5*cos(i*0.3+iTime*0.5),
                   0.7+0.3*sin(i*0.4+iTime*0.3), 1.0);
    vec4 contrib = col*exp(sin(i*i+iTime*0.7))/length(max(v,vec2(v.x*f*0.015,v.y*1.5)));
    // Scale contribution down per-streak so the streaks don't overpower
    o += contrib*(1.0+tailNoise*0.7)*smoothstep(0.0,1.0,i/20.0)*0.38;
  }
  o = tanh(pow(o/100.0, vec4(1.5)));
  gl_FragColor = o * 1.4;
}
`

// ---------------------------------------------------------------------------
// Star dot layers (layer 1 — drifting dots, now drawn on a single canvas).
// Same counts/colors as before; `speed` is px/sec derived from the old
// CSS keyframe (a 2000px tile travelled over the given duration).
// ---------------------------------------------------------------------------
interface Layer { size: number; count: number; speed: number; color: string }
const LAYERS: Layer[] = [
  { size: 1, count: 800, speed: 2000 / 90,  color: 'rgba(255,255,255,0.65)' },
  { size: 2, count: 340, speed: 2000 / 150, color: 'rgba(255,255,255,0.45)' },
  { size: 3, count: 140, speed: 2000 / 220, color: 'rgba(255,255,255,0.30)' },
]

interface Dot { x: number; y: number }

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function StarsBackground() {
  const starsRef = useRef<HTMLCanvasElement>(null)
  const auroraRef = useRef<HTMLDivElement>(null)

  // --- Star dots canvas (separate from the Three.js aurora canvas) ---
  useEffect(() => {
    const canvas = starsRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
    let w = window.innerWidth
    let h = window.innerHeight

    // Generate the dots once, in CSS pixel space spanning the viewport.
    // Y wraps over the viewport height so the upward drift loops seamlessly.
    const layers = LAYERS.map((l) => {
      const dots: Dot[] = []
      for (let i = 0; i < l.count; i++) {
        dots.push({ x: Math.random() * w, y: Math.random() * h })
      }
      return dots
    })

    const resize = () => {
      w = window.innerWidth
      h = window.innerHeight
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      canvas.style.width = '100%'
      canvas.style.height = '100%'
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    let frameId: number
    let start: number | null = null
    const tick = (now: number) => {
      if (start === null) start = now
      const t = (now - start) / 1000 // seconds elapsed
      ctx.clearRect(0, 0, w, h)
      for (let li = 0; li < LAYERS.length; li++) {
        const layer = LAYERS[li]
        const dots = layers[li]
        const drift = (layer.speed * t) % h
        ctx.fillStyle = layer.color
        const s = layer.size
        for (let i = 0; i < dots.length; i++) {
          const d = dots[i]
          // Drift upward, wrapping within [0, h)
          let yy = d.y - drift
          if (yy < 0) yy += h
          ctx.fillRect(d.x, yy, s, s)
        }
      }
      frameId = requestAnimationFrame(tick)
    }
    frameId = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(frameId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  // --- Aurora GLSL shader (capped at 30fps) ---
  useEffect(() => {
    const el = auroraRef.current
    if (!el) return

    const w = window.innerWidth
    const h = window.innerHeight

    const scene = new THREE.Scene()
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    renderer.setSize(w, h)
    // Canvas sits inside our absolutely-positioned div; pointer-events off
    renderer.domElement.style.position = 'absolute'
    renderer.domElement.style.inset = '0'
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    el.appendChild(renderer.domElement)

    const material = new THREE.ShaderMaterial({
      uniforms: {
        iTime:       { value: 0 },
        iResolution: { value: new THREE.Vector2(w, h) },
      },
      vertexShader:   VERT,
      fragmentShader: FRAG,
      transparent:    true,
    })
    scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material))

    let frameId: number
    let last = 0
    const FRAME_MS = 33 // ~30fps cap
    const tick = (now: number) => {
      frameId = requestAnimationFrame(tick)
      const delta = now - last
      // Only advance + render once >33ms have elapsed since the last frame
      if (delta < FRAME_MS) return
      last = now
      material.uniforms.iTime.value += 0.033
      renderer.render(scene, camera)
    }
    frameId = requestAnimationFrame(tick)

    const onResize = () => {
      const nw = window.innerWidth, nh = window.innerHeight
      renderer.setSize(nw, nh)
      material.uniforms.iResolution.value.set(nw, nh)
    }
    window.addEventListener('resize', onResize)

    return () => {
      cancelAnimationFrame(frameId)
      window.removeEventListener('resize', onResize)
      if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement)
      material.dispose()
      renderer.dispose()
    }
  }, [])

  return (
    <div style={{ position: 'fixed', inset: 0, overflow: 'hidden', pointerEvents: 'none', zIndex: 0 }}>
      {/* Layer 1: star dots drawn on a single canvas */}
      <canvas ref={starsRef} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }} />
      {/* Layer 2: Aurora GLSL shader — blended over the stars */}
      <div ref={auroraRef} style={{ position: 'absolute', inset: 0, opacity: 0.40, mixBlendMode: 'screen' }} />
    </div>
  )
}
