import { useState, useEffect } from 'react'
import { fetchAgentOps, AG_STATUS } from '../../data/fleet'
import type { AgentOp } from '../../data/fleet'

interface ProfilesProps {
  accent: string
}

export default function Profiles({ accent }: ProfilesProps) {
  const [profiles, setProfiles] = useState<AgentOp[]>([])
  const [selected, setSelected] = useState<AgentOp | null>(null)
  const [skillsCount, setSkillsCount] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false

    const refresh = async () => {
      const ops = await fetchAgentOps()
      if (cancelled) return
      if (ops.length > 0) setProfiles(ops)
    }

    refresh()
    const interval = setInterval(refresh, 15_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    fetch('/api/skills')
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setSkillsCount(data.length)
        else if (data && Array.isArray(data.skills)) setSkillsCount(data.skills.length)
      })
      .catch(() => {})
  }, [])

  const totalCount = profiles.length || 33
  const activeCount = profiles.filter((p) => p.status === 'busy' || p.status === 'online').length

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0, position: 'relative' }}>
      {/* Header */}
      <header style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div className="flex items-center justify-between" style={{ gap: 12 }}>
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Profiles</div>
            <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>
              {totalCount} active worker profiles
            </div>
          </div>
          <div className="flex items-center" style={{ gap: 8 }}>
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: '4px 10px',
                borderRadius: 99,
                background: `color-mix(in oklab, ${accent} 14%, transparent)`,
                border: `1px solid color-mix(in oklab, ${accent} 30%, transparent)`,
                color: accent,
              }}
            >
              Total: {totalCount}
            </span>
            <span
              style={{
                fontSize: 11,
                fontWeight: 600,
                padding: '4px 10px',
                borderRadius: 99,
                background: 'color-mix(in oklab, #4ade80 14%, transparent)',
                border: '1px solid color-mix(in oklab, #4ade80 30%, transparent)',
                color: '#4ade80',
              }}
            >
              Active: {activeCount}
            </span>
          </div>
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '22px 26px 36px' }}>
        <div style={{ maxWidth: 1120, margin: '0 auto' }}>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 14,
            }}
          >
            {profiles.map((a) => {
              const st = AG_STATUS[a.status]
              const initial = a.avatar || a.name[0].toUpperCase()
              const isActive = a.status === 'busy' || a.status === 'online'
              return (
                <div
                  key={a.name}
                  onClick={() => setSelected(a)}
                  className="relative overflow-hidden"
                  style={{
                    background: 'var(--s3)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderTop: `2px solid ${a.color}`,
                    borderRadius: 16,
                    padding: 16,
                    cursor: 'pointer',
                    transition: 'transform 0.28s cubic-bezier(0.16,1,0.3,1), box-shadow 0.28s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-3px)'
                    e.currentTarget.style.boxShadow = '0 14px 32px rgba(0,0,0,0.44)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'none'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  {/* Glow orb */}
                  <span
                    style={{
                      position: 'absolute',
                      right: -34,
                      top: -38,
                      width: 110,
                      height: 110,
                      borderRadius: '50%',
                      background: `color-mix(in oklab, ${a.color} 20%, transparent)`,
                      filter: 'blur(30px)',
                      pointerEvents: 'none',
                    }}
                  />

                  {/* Top row: avatar + name + active badge */}
                  <div className="relative flex items-start" style={{ gap: 12 }}>
                    <span
                      className="flex flex-none items-center justify-center"
                      style={{
                        width: 42,
                        height: 42,
                        borderRadius: 12,
                        fontFamily: 'var(--font-display)',
                        fontWeight: 700,
                        fontSize: 16,
                        color: a.color,
                        background: `color-mix(in oklab, ${a.color} 16%, transparent)`,
                        border: `1px solid color-mix(in oklab, ${a.color} 38%, transparent)`,
                      }}
                    >
                      {initial}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="mono" style={{ fontSize: 14.5, fontWeight: 600, color: '#f0f2f8' }}>{a.name}</div>
                      <div style={{ fontSize: 12, color: '#9aa0b4', marginTop: 2 }}>{a.role}</div>
                    </div>
                    {isActive && (
                      <span
                        style={{
                          flex: 'none',
                          fontSize: 9,
                          fontWeight: 700,
                          letterSpacing: '0.05em',
                          padding: '2px 7px',
                          borderRadius: 99,
                          color: accent,
                          background: `color-mix(in oklab, ${accent} 14%, transparent)`,
                          border: `1px solid color-mix(in oklab, ${accent} 28%, transparent)`,
                        }}
                      >
                        ACTIVE
                      </span>
                    )}
                  </div>

                  {/* Model row */}
                  <div className="relative" style={{ marginTop: 11, fontSize: 11.5, color: '#6a7088' }}>
                    <span className="mono">{a.model}</span>
                  </div>

                  {/* Status */}
                  <div className="relative flex items-center justify-between" style={{ gap: 8, marginTop: 10 }}>
                    <span
                      className="inline-flex items-center"
                      style={{
                        gap: 5,
                        fontSize: 10,
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        color: st.color,
                        background: `color-mix(in oklab, ${st.color} 12%, transparent)`,
                        border: `1px solid color-mix(in oklab, ${st.color} 28%, transparent)`,
                        borderRadius: 99,
                        padding: '3px 9px',
                      }}
                    >
                      <span style={{ width: 5, height: 5, borderRadius: '50%', background: st.color }} />
                      {st.label}
                    </span>
                    <span className="mono" style={{ fontSize: 11, color: '#6a7088' }}>{a.success}% success</span>
                  </div>

                  {/* Stats row */}
                  <div className="relative flex items-center" style={{ gap: 16, marginTop: 12, fontSize: 11.5 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                      <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 18, color: 'var(--text-primary)', lineHeight: 1 }}>{a.today}</span>
                      <span style={{ fontSize: 10, color: '#6a7088' }}>today</span>
                    </div>
                    <div style={{ width: 1, height: 28, background: 'rgba(255,255,255,0.06)' }} />
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                      <span className="mono" style={{ fontWeight: 600, fontSize: 13, color: '#c6cad8' }}>{a.completed}/{a.total}</span>
                      <span style={{ fontSize: 10, color: '#6a7088' }}>completed</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Detail Drawer */}
      {selected && (
        <>
          {/* Backdrop */}
          <div
            onClick={() => setSelected(null)}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 40,
              background: 'rgba(0,0,0,0.35)',
            }}
          />

          {/* Drawer panel */}
          <div
            style={{
              position: 'fixed',
              top: 0,
              right: 0,
              bottom: 0,
              zIndex: 50,
              width: 360,
              background: '#0d121d',
              borderLeft: '1px solid rgba(255,255,255,0.08)',
              display: 'flex',
              flexDirection: 'column',
              overflowY: 'auto',
              animation: 'slideInRight 0.28s cubic-bezier(0.16,1,0.3,1)',
            }}
          >
            {/* Drawer header */}
            <div
              style={{
                flex: 'none',
                padding: '20px 22px 16px',
                borderBottom: '1px solid rgba(255,255,255,0.07)',
                display: 'flex',
                alignItems: 'flex-start',
                gap: 14,
              }}
            >
              <span
                className="flex flex-none items-center justify-center"
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: 15,
                  fontFamily: 'var(--font-display)',
                  fontWeight: 700,
                  fontSize: 20,
                  color: selected.color,
                  background: `color-mix(in oklab, ${selected.color} 16%, transparent)`,
                  border: `1px solid color-mix(in oklab, ${selected.color} 38%, transparent)`,
                }}
              >
                {selected.avatar || selected.name[0].toUpperCase()}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="mono" style={{ fontWeight: 700, fontSize: 16, color: '#f0f2f8' }}>{selected.name}</div>
                <div style={{ fontSize: 12, color: '#9aa0b4', marginTop: 3 }}>{selected.role}</div>
              </div>
              <button
                onClick={() => setSelected(null)}
                style={{
                  flex: 'none',
                  width: 30,
                  height: 30,
                  borderRadius: 8,
                  background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: '#9aa0b4',
                  fontSize: 16,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  lineHeight: 1,
                }}
              >
                ×
              </button>
            </div>

            {/* Drawer body */}
            <div style={{ flex: 1, padding: '18px 22px 32px', display: 'flex', flexDirection: 'column', gap: 20 }}>
              {/* Status + success */}
              <div style={{ display: 'flex', gap: 10 }}>
                {(() => {
                  const st = AG_STATUS[selected.status]
                  return (
                    <span
                      className="inline-flex items-center"
                      style={{
                        gap: 6,
                        fontSize: 11,
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        color: st.color,
                        background: `color-mix(in oklab, ${st.color} 12%, transparent)`,
                        border: `1px solid color-mix(in oklab, ${st.color} 28%, transparent)`,
                        borderRadius: 99,
                        padding: '4px 11px',
                      }}
                    >
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: st.color }} />
                      {st.label}
                    </span>
                  )
                })()}
                <span
                  style={{
                    fontSize: 11,
                    fontWeight: 600,
                    padding: '4px 11px',
                    borderRadius: 99,
                    background: `color-mix(in oklab, ${accent} 12%, transparent)`,
                    border: `1px solid color-mix(in oklab, ${accent} 28%, transparent)`,
                    color: accent,
                  }}
                >
                  {selected.success}% success
                </span>
              </div>

              {/* Stats table */}
              <div
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid rgba(255,255,255,0.07)',
                  borderRadius: 12,
                  overflow: 'hidden',
                }}
              >
                {[
                  { label: 'Model', value: selected.model, mono: true },
                  { label: 'Provider', value: selected.model },
                  { label: 'Tasks today', value: String(selected.today) },
                  { label: 'Completed', value: `${selected.completed} / ${selected.total}` },
                  { label: 'Last active', value: selected.lastActive },
                  ...(skillsCount !== null ? [{ label: 'Skills', value: String(skillsCount) }] : []),
                ].map((row, i, arr) => (
                  <div
                    key={row.label}
                    className="flex items-center justify-between"
                    style={{
                      padding: '10px 14px',
                      fontSize: 12.5,
                      borderBottom: i < arr.length - 1 ? '1px solid rgba(255,255,255,0.05)' : 'none',
                    }}
                  >
                    <span style={{ color: '#6a7088' }}>{row.label}</span>
                    <span className={row.mono ? 'mono' : ''} style={{ color: '#c6cad8', fontWeight: 500 }}>
                      {row.value}
                    </span>
                  </div>
                ))}
              </div>

              {/* Last active timestamp */}
              <div style={{ fontSize: 11, color: '#565d72', textAlign: 'center' }}>
                Last active: {selected.lastActive}
              </div>
            </div>
          </div>
        </>
      )}

      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);   opacity: 1; }
        }
      `}</style>
    </div>
  )
}
