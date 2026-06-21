import { useMemo, useState } from 'react'
import { SKILLS } from '../../data/skills'

interface SkillsProps {
  accent: string
}

export default function Skills({ accent }: SkillsProps) {
  // Enabled state per skill id, seeded from the data's `on` flag.
  const [enabled, setEnabled] = useState<Record<string, boolean>>(() =>
    SKILLS.reduce((m, s) => {
      m[s.id] = s.on
      return m
    }, {} as Record<string, boolean>),
  )
  const [selId, setSelId] = useState<string | null>(null)

  const toggle = (id: string) => setEnabled((m) => ({ ...m, [id]: !m[id] }))

  const detail = useMemo(() => SKILLS.find((s) => s.id === selId) ?? null, [selId])
  const detailOn = detail ? enabled[detail.id] : false

  return (
    <div className="relative flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Skills</div>
        <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>tools the agent can call — click a skill for details, toggle to enable</div>
      </header>

      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '22px 26px 32px' }}>
        <div style={{ maxWidth: 1080, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
          {SKILLS.map((p) => {
            const on = enabled[p.id]
            const sel = selId === p.id
            const selBorder = sel ? accent : on ? `color-mix(in oklab, ${accent} 28%, transparent)` : 'rgba(255,255,255,0.06)'
            return (
              <div
                key={p.id}
                onClick={() => setSelId(p.id)}
                className="flex flex-col"
                style={{
                  background: 'var(--s3)',
                  border: `1px solid ${selBorder}`,
                  borderRadius: 12,
                  padding: 16,
                  gap: 11,
                  cursor: 'pointer',
                  transition: 'transform 0.28s cubic-bezier(0.16,1,0.3,1), border-color 0.28s, box-shadow 0.28s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-4px)'
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.28)'
                  e.currentTarget.style.boxShadow = '0 14px 34px rgba(0,0,0,0.45)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'none'
                  e.currentTarget.style.borderColor = selBorder
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                <div className="flex items-start" style={{ gap: 11 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: on ? '#4ade80' : '#565d72', marginTop: 6, flex: 'none', boxShadow: `0 0 8px ${on ? '#4ade80' : '#565d72'}` }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="flex items-center" style={{ gap: 8 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: '#f0f2f8' }}>{p.name}</span>
                      <span style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#818799', background: 'rgba(255,255,255,0.05)', borderRadius: 5, padding: '2px 6px' }}>{p.cat}</span>
                    </div>
                    <div style={{ fontSize: 12.5, lineHeight: 1.5, color: '#9aa0b4', marginTop: 5, textWrap: 'pretty' }}>{p.desc}</div>
                  </div>
                  {/* Toggle — stopPropagation so flipping does NOT open the drawer */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      toggle(p.id)
                    }}
                    aria-label={`${on ? 'Disable' : 'Enable'} ${p.name}`}
                    className="relative flex-none"
                    style={{ width: 38, height: 22, borderRadius: 12, border: 'none', background: on ? accent : 'rgba(255,255,255,0.12)', cursor: 'pointer', transition: 'background 0.15s' }}
                  >
                    <span style={{ position: 'absolute', top: 2, left: on ? 18 : 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', transition: 'left 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.4)' }} />
                  </button>
                </div>
                <div className="flex flex-wrap" style={{ gap: 5 }}>
                  {p.skills.map((k) => (
                    <span key={k} className="mono" style={{ fontSize: 10, color: '#9298ab', background: 'rgba(255,255,255,0.045)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 5, padding: '2px 7px' }}>
                      {k}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Skill info drawer */}
      {detail && (
        <>
          <div
            onClick={() => setSelId(null)}
            style={{ position: 'absolute', inset: 0, zIndex: 30, background: 'rgba(4,6,10,0.5)', backdropFilter: 'blur(2px)', animation: 'hscrimin 0.2s ease' }}
          />
          <div
            className="flex flex-col"
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              bottom: 0,
              zIndex: 31,
              width: 452,
              maxWidth: '90%',
              background: '#0b0f17',
              borderLeft: '1px solid rgba(255,255,255,0.1)',
              boxShadow: '-22px 0 60px rgba(0,0,0,0.5)',
              minHeight: 0,
              animation: 'hdrawerin 0.3s cubic-bezier(0.16,1,0.3,1)',
            }}
          >
            <div style={{ flex: 'none', height: 3, background: accent, boxShadow: `0 0 16px ${accent}` }} />
            <div className="flex flex-none items-start justify-between" style={{ gap: 14, padding: '20px 22px 0' }}>
              <div style={{ minWidth: 0 }}>
                <span style={{ display: 'inline-block', fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#818799', background: 'rgba(255,255,255,0.05)', borderRadius: 5, padding: '3px 7px' }}>{detail.cat}</span>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 25, letterSpacing: '0.01em', color: 'var(--text-primary)', marginTop: 11 }}>{detail.name}</div>
                <div
                  className="inline-flex items-center"
                  style={{ gap: 7, marginTop: 9, fontSize: 11, fontWeight: 600, color: detailOn ? '#4ade80' : '#6a7088', background: detailOn ? 'rgba(74,222,128,0.12)' : 'rgba(255,255,255,0.05)', borderRadius: 7, padding: '4px 9px' }}
                >
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: detailOn ? '#4ade80' : '#6a7088', boxShadow: `0 0 7px ${detailOn ? '#4ade80' : '#6a7088'}` }} />
                  {detailOn ? 'Enabled' : 'Disabled'}
                </div>
              </div>
              <button
                onClick={() => setSelId(null)}
                className="inline-flex flex-none items-center justify-center"
                style={{ width: 32, height: 32, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 9, color: '#9aa0b4', cursor: 'pointer', transition: 'color 0.15s, background 0.15s' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.color = '#f4f6fb'
                  e.currentTarget.style.background = 'rgba(255,255,255,0.1)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.color = '#9aa0b4'
                  e.currentTarget.style.background = 'rgba(255,255,255,0.05)'
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '20px 22px 26px' }}>
              <p style={{ fontSize: 13.5, lineHeight: 1.62, color: 'var(--text-body)', textWrap: 'pretty', margin: 0 }}>{detail.long}</p>

              {/* Meta grid */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, marginTop: 20, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 11, overflow: 'hidden' }}>
                <div style={{ background: 'var(--s3)', padding: '12px 14px' }}>
                  <div style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6a7088' }}>Author</div>
                  <div style={{ fontSize: 13, color: '#d4d8e4', marginTop: 4 }}>{detail.author}</div>
                </div>
                <div style={{ background: 'var(--s3)', padding: '12px 14px' }}>
                  <div style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6a7088' }}>Version</div>
                  <div className="mono" style={{ fontSize: 13, color: '#d4d8e4', marginTop: 4 }}>v{detail.version}</div>
                </div>
                <div style={{ background: 'var(--s3)', padding: '12px 14px' }}>
                  <div style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6a7088' }}>Scope</div>
                  <div style={{ fontSize: 13, color: '#d4d8e4', marginTop: 4 }}>{detail.scope}</div>
                </div>
                <div style={{ background: 'var(--s3)', padding: '12px 14px' }}>
                  <div style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6a7088' }}>Calls · 7d</div>
                  <div className="mono" style={{ fontSize: 13, color: '#d4d8e4', marginTop: 4 }}>{detail.calls7d.toLocaleString()}</div>
                </div>
              </div>

              {/* Command list — staggered reveal */}
              <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6a7088', margin: '24px 0 12px' }}>Commands</div>
              <div className="flex flex-col" style={{ gap: 9 }}>
                {detail.commands.map((c, i) => (
                  <div
                    key={c.name}
                    style={{ background: 'var(--s3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: '13px 14px', animation: 'hcmdrow 0.34s cubic-bezier(0.16,1,0.3,1) both', animationDelay: `${(i * 0.05).toFixed(2)}s` }}
                  >
                    <div className="mono" style={{ fontSize: 12, color: accent }}>{c.sig}</div>
                    <div style={{ fontSize: 12.5, lineHeight: 1.55, color: '#9aa0b4', marginTop: 6, textWrap: 'pretty' }}>{c.desc}</div>
                  </div>
                ))}
              </div>

              {/* Toggle button */}
              <button
                onClick={() => toggle(detail.id)}
                className="flex w-full items-center justify-center"
                style={{
                  gap: 10,
                  marginTop: 22,
                  padding: 12,
                  borderRadius: 11,
                  background: detailOn ? 'rgba(255,255,255,0.05)' : accent,
                  border: detailOn ? '1px solid rgba(255,255,255,0.12)' : '1px solid transparent',
                  color: detailOn ? '#c6cad8' : '#1c1404',
                  fontFamily: 'inherit',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'filter 0.15s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.filter = 'brightness(1.08)')}
                onMouseLeave={(e) => (e.currentTarget.style.filter = 'none')}
              >
                <span className="relative flex-none" style={{ width: 38, height: 22, borderRadius: 12, background: detailOn ? accent : 'rgba(255,255,255,0.18)', transition: 'background 0.15s' }}>
                  <span style={{ position: 'absolute', top: 2, left: detailOn ? 18 : 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', transition: 'left 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.4)' }} />
                </span>
                {detailOn ? 'Disable skill' : 'Enable skill'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
