import { useEffect, useMemo, useState } from 'react'
import { ACCENT } from '../../data/agents'
import { buildGalaxy, galaxyDecor } from '../../data/phase3'
import type { GalaxySelection, MemNode } from '../../data/phase3'
import { useGalaxy } from '../memory/useGalaxy'
import '../../styles/phase3.css'

interface MemoryProps {
  accent?: string
}

export default function Memory({ accent = ACCENT }: MemoryProps) {
  const data = useMemo(() => buildGalaxy(), [])
  const [paused, setPaused] = useState(false)
  const [sel, setSel] = useState<GalaxySelection | null>(null)

  const onSelect = (node: MemNode) => setSel(galaxyDecor(node))
  const canvasRef = useGalaxy({ data, paused, selectedId: sel?.id ?? null, onSelect })

  // Spacebar toggles pause — ignored while focus is in an input/textarea/select.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === 'Space' || e.key === ' ') {
        const t = e.target as HTMLElement | null
        if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return
        e.preventDefault()
        setPaused((p) => !p)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const pauseDot = paused ? accent : '#4ade80'
  const pauseLabel = paused ? 'Paused' : 'Orbiting'

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header className="flex flex-wrap items-center justify-between" style={{ flex: 'none', padding: '14px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)', gap: 16 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Memory Galaxy</div>
          <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>
            {data.nodes.length} memories · drag to orbit · scroll to zoom · click a star to inspect · space to pause
          </div>
        </div>
        <div className="flex flex-wrap items-center" style={{ gap: 7 }}>
          {data.tiers.map((t) => (
            <span key={t.id} className="inline-flex items-center" style={{ gap: 6, fontSize: 11, color: 'var(--text-muted)', background: 'var(--s4)', border: '1px solid var(--border)', borderRadius: 7, padding: '4px 9px' }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: t.color, boxShadow: `0 0 7px ${t.color}` }} />
              {t.label} <span className="mono" style={{ color: '#6a7088' }}>{t.count}</span>
            </span>
          ))}
        </div>
      </header>

      <div className="relative" style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%', cursor: 'grab' }} />

        {/* Pause pill (mirrors spacebar state) */}
        <button
          onClick={() => setPaused((p) => !p)}
          className="inline-flex items-center"
          style={{ position: 'absolute', left: 22, top: 18, zIndex: 5, gap: 8, background: 'rgba(12,17,25,0.78)', backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '7px 12px', fontFamily: 'inherit', fontSize: 11.5, fontWeight: 600, color: '#c6cad8', cursor: 'pointer', transition: 'border-color 0.15s' }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.26)')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')}
        >
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: pauseDot, boxShadow: `0 0 7px ${pauseDot}` }} />
          {pauseLabel}
        </button>

        {/* Selected node info card */}
        {sel && (
          <div style={{ position: 'absolute', right: 22, bottom: 22, width: 300, background: 'rgba(13,18,28,0.92)', backdropFilter: 'blur(10px)', border: '1px solid rgba(255,255,255,0.12)', borderLeft: `3px solid ${sel.color}`, borderRadius: 12, padding: 16, boxShadow: '0 16px 40px rgba(0,0,0,0.5)', zIndex: 6, animation: 'hdrawerin 0.24s var(--ease-out)' }}>
            <div className="flex items-center justify-between" style={{ gap: 10 }}>
              <span className="inline-flex items-center" style={{ gap: 7, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: sel.color }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: sel.color, boxShadow: `0 0 8px ${sel.color}` }} />
                {sel.tierLabel}
              </span>
              <button onClick={() => setSel(null)} style={{ background: 'none', border: 'none', color: '#818799', fontSize: 17, lineHeight: 1, cursor: 'pointer', padding: 0 }} onMouseEnter={(e) => (e.currentTarget.style.color = '#e9ebf2')} onMouseLeave={(e) => (e.currentTarget.style.color = '#818799')}>×</button>
            </div>
            <div style={{ fontSize: 14.5, fontWeight: 600, color: '#f0f2f8', marginTop: 10, lineHeight: 1.35 }}>{sel.title}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 7, lineHeight: 1.55 }}>{sel.detail}</div>
            <div className="flex items-center" style={{ gap: 18, marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
              {[
                { l: 'Importance', v: sel.importance },
                { l: 'Recall', v: sel.recall },
                { l: 'Age', v: sel.age },
              ].map((x) => (
                <div key={x.l}>
                  <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088' }}>{x.l}</div>
                  <div className="mono" style={{ fontSize: 13, color: '#e4e6ee', marginTop: 2 }}>{x.v}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
