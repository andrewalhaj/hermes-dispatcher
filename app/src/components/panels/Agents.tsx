import { useState, useEffect } from 'react'
import { AG_STATUS, agentOps, fleetSummary, fetchAgentOps, fetchFleetSummary } from '../../data/fleet'
import type { AgentOp, FleetMetric } from '../../data/fleet'
import { tileBlurb } from '../../data/info'
import { useInfo } from '../TileInfoDrawer'
import { profileDisplayName } from '../../data/profileDisplayNames'

interface AgentsProps {
  accent: string
}

export default function Agents({ accent }: AgentsProps) {
  const { openInfo } = useInfo()
  const [ops, setOps] = useState<AgentOp[]>(() => agentOps(accent))
  const [summary, setSummary] = useState<FleetMetric[]>(() => fleetSummary(accent))

  useEffect(() => {
    let cancelled = false

    const refresh = async () => {
      const [newOps, newSummary] = await Promise.all([fetchAgentOps(), fetchFleetSummary()])
      if (cancelled) return
      if (newOps.length > 0) setOps(newOps)
      if (newSummary.length > 0) setSummary(newSummary)
    }

    refresh()
    const interval = setInterval(refresh, 15_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [])

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Agent operations</div>
        <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>
          Live status across the worker pool — Hermes, executor, coder-c, coder-d, coder-e.
        </div>
      </header>

      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '22px 26px 36px' }}>
        <div style={{ maxWidth: 1120, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* Fleet summary tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
            {summary.map((m) => (
              <div
                key={m.label}
                onClick={() =>
                  openInfo({
                    category: 'Fleet metric',
                    title: m.label,
                    value: m.value,
                    accent: m.color,
                    desc: tileBlurb(m.label),
                    stats: [
                      { label: 'Value', value: m.value },
                      { label: 'Window', value: 'today' },
                    ],
                  })
                }
                className="relative overflow-hidden"
                style={{ background: 'var(--s3)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 13, padding: '15px 16px', cursor: 'pointer', transition: 'transform 0.25s, border-color 0.25s, box-shadow 0.25s' }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-4px)'
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)'
                  e.currentTarget.style.boxShadow = '0 14px 34px rgba(0,0,0,0.45)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'none'
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, background: m.color }} />
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 25, lineHeight: 1, color: m.color }}>{m.value}</div>
                <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088', marginTop: 7 }}>{m.label}</div>
              </div>
            ))}
          </div>

          {/* Agent cards */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 14 }}>
            {ops.map((a) => {
              const st = AG_STATUS[a.status]
              const progW = `${Math.min(100, a.today * 12 + 4)}%`
              return (
                <div
                  key={a.name}
                  onClick={() =>
                    openInfo({
                      category: `Agent · ${st.label}`,
                      title: profileDisplayName(a.name),
                      accent: a.color,
                      desc: `${a.role} — ${a.completed} of ${a.total} assigned tasks complete, ${a.success}% success rate.`,
                      stats: [
                        { label: 'Status', value: st.label },
                        { label: 'Success rate', value: `${a.success}%` },
                        { label: 'Tasks today', value: String(a.today) },
                        { label: 'Completed', value: `${a.completed} / ${a.total}` },
                        { label: 'Model', value: a.model },
                        { label: 'Last active', value: a.lastActive },
                      ],
                      actionLabel: `Open chat with ${profileDisplayName(a.name)}`,
                    })
                  }
                  className="relative overflow-hidden"
                  style={{ background: 'var(--s3)', border: '1px solid rgba(255,255,255,0.06)', borderTop: `2px solid ${a.color}`, borderRadius: 16, padding: 17, cursor: 'pointer', transition: 'transform 0.28s cubic-bezier(0.16,1,0.3,1), border-color 0.28s, box-shadow 0.28s' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-4px)'
                    e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)'
                    e.currentTarget.style.boxShadow = '0 14px 34px rgba(0,0,0,0.45)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'none'
                    e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  <span style={{ position: 'absolute', right: -38, top: -42, width: 120, height: 120, borderRadius: '50%', background: `color-mix(in oklab, ${a.color} 22%, transparent)`, filter: 'blur(34px)', pointerEvents: 'none' }} />
                  <div className="relative flex items-start" style={{ gap: 12 }}>
                    <span
                      className="flex flex-none items-center justify-center"
                      style={{ width: 44, height: 44, borderRadius: 13, fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 17, color: a.color, background: `color-mix(in oklab, ${a.color} 16%, transparent)`, border: `1px solid color-mix(in oklab, ${a.color} 40%, transparent)` }}
                    >
                      {a.avatar}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="mono" style={{ fontSize: 14.5, fontWeight: 600, color: '#f0f2f8' }}>{profileDisplayName(a.name)}</div>
                      <div style={{ fontSize: 12, color: '#9aa0b4', marginTop: 2 }}>{a.role}</div>
                    </div>
                    <span className="relative flex-none" style={{ width: 44, height: 44 }}>
                      <svg width="44" height="44" viewBox="0 0 36 36">
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="3" />
                        <circle cx="18" cy="18" r="15.9" fill="none" stroke={a.color} strokeWidth="3" strokeLinecap="round" pathLength={100} strokeDasharray={`${a.success} ${100 - a.success}`} transform="rotate(-90 18 18)" />
                      </svg>
                      <span className="mono absolute inset-0 flex items-center justify-center" style={{ fontSize: 10, fontWeight: 700, color: '#e4e6ee' }}>{a.success}%</span>
                    </span>
                  </div>
                  <div className="relative flex items-center justify-between" style={{ gap: 10, marginTop: 14 }}>
                    <span
                      className="inline-flex items-center"
                      style={{ gap: 6, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: st.color, background: `color-mix(in oklab, ${st.color} 12%, transparent)`, border: `1px solid color-mix(in oklab, ${st.color} 28%, transparent)`, borderRadius: 99, padding: '3px 9px' }}
                    >
                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: st.color }} />
                      {st.label}
                    </span>
                    <span className="mono" style={{ fontSize: 11, color: '#6a7088' }}>{a.completed}/{a.total} complete</span>
                  </div>
                  <div className="relative flex items-baseline" style={{ gap: 7, marginTop: 14 }}>
                    <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 24, color: 'var(--text-primary)', lineHeight: 1 }}>{a.today}</span>
                    <span style={{ fontSize: 11, color: '#6a7088' }}>tasks today</span>
                  </div>
                  <div className="relative" style={{ height: 3, borderRadius: 99, background: 'rgba(255,255,255,0.06)', overflow: 'hidden', margin: '11px 0 13px' }}>
                    <span style={{ display: 'block', height: '100%', width: progW, borderRadius: 99, background: a.color, boxShadow: `0 0 14px ${a.color}` }} />
                  </div>
                  <div className="relative flex flex-col" style={{ gap: 7 }}>
                    <div className="flex items-center justify-between" style={{ gap: 10, fontSize: 11.5 }}>
                      <span style={{ color: '#6a7088' }}>Model</span>
                      <span className="mono" style={{ color: '#c6cad8' }}>{a.model}</span>
                    </div>
                    <div className="flex items-center justify-between" style={{ gap: 10, fontSize: 11.5 }}>
                      <span style={{ color: '#6a7088' }}>Last active</span>
                      <span style={{ color: '#c6cad8' }}>{a.lastActive}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
