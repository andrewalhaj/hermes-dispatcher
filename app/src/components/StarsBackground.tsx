import { useEffect, useRef, useMemo } from 'react'
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
  vec2 shake = vec2(sin(iTime*1.2)*0.005, cos(iTime*2.1)*0.005);
  vec2 p = ((gl_FragCoord.xy + shake*iResolution.xy) - iResolution.xy*0.5)
           / iResolution.y * mat2(6.0,-4.0,4.0,6.0);
  vec2 v; vec4 o = vec4(0.0);
  float f = 2.0 + fbm(p + vec2(iTime*5.0,0.0))*0.5;
  for(float i=0.0;i<35.0;i++){
    v = p + cos(i*i+(iTime+p.x*0.08)*0.025+i*vec2(13.0,11.0))*3.5
        + vec2(sin(iTime*3.0+i)*0.003, cos(iTime*3.5-i)*0.003);
    float tailNoise = fbm(v+vec2(iTime*0.5,i))*0.3*(1.0-(i/35.0));
    vec4 col = vec4(0.1+0.3*sin(i*0.2+iTime*0.4), 0.3+0.5*cos(i*0.3+iTime*0.5),
                   0.7+0.3*sin(i*0.4+iTime*0.3), 1.0);
    vec4 contrib = col*exp(sin(i*i+iTime*0.8))/length(max(v,vec2(v.x*f*0.015,v.y*1.5)));
    o += contrib*(1.0+tailNoise*0.8)*smoothstep(0.0,1.0,i/35.0)*0.6;
  }
  o = tanh(pow(o/100.0, vec4(1.6)));
  gl_FragColor = o * 1.5;
}
`

// ---------------------------------------------------------------------------
// CSS star layers (layer 1 — the original drifting dots)
// ---------------------------------------------------------------------------
interface Layer { size: number; count: number; duration: string; color: string }
const LAYERS: Layer[] = [
  { size: 1, count: 560, duration: '90s',  color: 'rgba(255,255,255,0.65)' },
  { size: 2, count: 220, duration: '150s', color: 'rgba(255,255,255,0.45)' },
  { size: 3, count: 90,  duration: '220s', color: 'var(--ac, #f6b73c)' },
]

function genBoxShadow(count: number, color: string): string {
  const parts: string[] = []
  for (let i = 0; i < count; i++) {
    parts.push(`${Math.floor(Math.random()*1600)}px ${Math.floor(Math.random()*2000)}px 0 ${color}`)
  }
  return parts.join(', ')
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function StarsBackground() {
  const auroraRef = useRef<HTMLDivElement>(null)
  const shadows = useMemo(() => LAYERS.map((l) => genBoxShadow(l.count, l.color)), [])

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
    const tick = () => {
      material.uniforms.iTime.value += 0.016
      renderer.render(scene, camera)
      frameId = requestAnimationFrame(tick)
    }
    tick()

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
      {/* Layer 1: CSS drifting star dots */}
      {LAYERS.map((layer, i) => (
        <div key={i} style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: 2000,
          animation: `hstars ${layer.duration} linear infinite` }}>
          <span style={{ position: 'absolute', top: 0, left: 0, width: layer.size, height: layer.size,
            borderRadius: '50%', background: 'transparent', boxShadow: shadows[i] }} />
          <span style={{ position: 'absolute', top: 2000, left: 0, width: layer.size, height: layer.size,
            borderRadius: '50%', background: 'transparent', boxShadow: shadows[i] }} />
        </div>
      ))}
      {/* Layer 2: Aurora GLSL shader — blended over the stars */}
      <div ref={auroraRef} style={{ position: 'absolute', inset: 0, opacity: 0.55, mixBlendMode: 'screen' }} />
    </div>
  )
}
