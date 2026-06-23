import { useId } from 'react'
import Particles, { ParticlesProvider, useParticlesProvider } from '@tsparticles/react'
import { loadSlim } from '@tsparticles/slim'
import type { Engine } from '@tsparticles/engine'

type SparklesCoreProps = {
  id?: string
  className?: string
  background?: string
  minSize?: number
  maxSize?: number
  speed?: number
  particleColor?: string
  particleDensity?: number
}

async function particlesInit(engine: Engine) {
  await loadSlim(engine)
}

function SparklesInner(props: SparklesCoreProps) {
  const { id, minSize, maxSize, speed, particleColor, particleDensity, background } = props
  const { loaded } = useParticlesProvider()
  const generatedId = useId()

  if (!loaded) return null

  return (
    <Particles
      id={id || generatedId}
      style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
      options={{
        background: { color: { value: background || 'transparent' } },
        fullScreen: { enable: false, zIndex: 0 },
        fpsLimit: 120,
        interactivity: {
          events: {
            onClick: { enable: false },
            onHover: { enable: false },
          },
        },
        particles: {
          color: { value: particleColor || '#ffffff' },
          move: {
            direction: 'none',
            enable: true,
            outModes: { default: 'out' },
            random: false,
            speed: { min: 0.1, max: speed ?? 1 },
            straight: false,
          },
          number: {
            density: { enable: true, width: 400, height: 400 },
            value: particleDensity ?? 80,
          },
          opacity: {
            value: { min: 0.1, max: 1 },
            animation: { enable: true, speed: speed ?? 4, sync: false },
          },
          shape: { type: 'circle' },
          size: { value: { min: minSize ?? 0.6, max: maxSize ?? 1.4 } },
        },
        detectRetina: true,
      }}
    />
  )
}

export function SparklesCore(props: SparklesCoreProps) {
  return (
    <ParticlesProvider init={particlesInit}>
      <SparklesInner {...props} />
    </ParticlesProvider>
  )
}

export default SparklesCore
