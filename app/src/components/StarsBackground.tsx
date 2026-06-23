import { useEffect, useRef, useId } from 'react'
import * as THREE from 'three'
import Particles, { ParticlesProvider, useParticlesProvider } from '@tsparticles/react'
import { loadSlim } from '@tsparticles/slim'
import type { Engine } from '@tsparticles/engine'

// ---------------------------------------------------------------------------
// Aurora shader (layer 2)
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
// tsParticles star field (layer 1)
// ---------------------------------------------------------------------------
async function particlesInit(engine: Engine) {
  await loadSlim(engine)
}

function StarField() {
  const { loaded } = useParticlesProvider()
  const id = useId()
  if (!loaded) return null
  return (
    <Particles
      id={id}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      options={{
        background: { color: { value: 'transparent' } },
        fullScreen: { enable: false, zIndex: 0 },
        fpsLimit: 60,
        interactivity: { events: { onClick: { enable: false }, onHover: { enable: false } } },
        particles: {
          color: { value: ['#ffffff', '#fffbe6', '#cce8ff'] },
          move: {
            direction: 'none',
            enable: true,
            outModes: { default: 'out' },
            speed: { min: 0.05, max: 0.25 },
            random: true,
            straight: false,
          },
          number: {
            density: { enable: true, width: 1200, height: 900 },
            value: 320,
          },
          opacity: {
            value: { min: 0.15, max: 0.9 },
            animation: { enable: true, speed: 0.8, sync: false },
          },
          shape: { type: 'circle' },
          size: { value: { min: 0.4, max: 1.8 } },
        },
        detectRetina: true,
      }}
    />
  )
}

// ---------------------------------------------------------------------------
// Aurora canvas (layer 2)
// ---------------------------------------------------------------------------
function AuroraCanvas() {
  const mountRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = mountRef.current
    if (!el) return
    const w = window.innerWidth, h = window.innerHeight
    const scene = new THREE.Scene()
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    renderer.setSize(w, h)
    renderer.domElement.style.cssText = 'position:absolute;inset:0;width:100%;height:100%'
    el.appendChild(renderer.domElement)
    const material = new THREE.ShaderMaterial({
      uniforms: { iTime: { value: 0 }, iResolution: { value: new THREE.Vector2(w, h) } },
      vertexShader: VERT, fragmentShader: FRAG, transparent: true,
    })
    scene.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material))
    let raf: number
    const tick = () => { material.uniforms.iTime.value += 0.016; renderer.render(scene, camera); raf = requestAnimationFrame(tick) }
    tick()
    const onResize = () => { const nw = window.innerWidth, nh = window.innerHeight; renderer.setSize(nw, nh); material.uniforms.iResolution.value.set(nw, nh) }
    window.addEventListener('resize', onResize)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', onResize); if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement); material.dispose(); renderer.dispose() }
  }, [])
  return <div ref={mountRef} style={{ position: 'absolute', inset: 0, opacity: 0.5, mixBlendMode: 'screen' }} />
}

// ---------------------------------------------------------------------------
// Composed background
// ---------------------------------------------------------------------------
export default function StarsBackground() {
  return (
    <div style={{ position: 'fixed', inset: 0, overflow: 'hidden', pointerEvents: 'none', zIndex: 0 }}>
      <ParticlesProvider init={particlesInit}>
        <StarField />
      </ParticlesProvider>
      <AuroraCanvas />
    </div>
  )
}
