import { useMemo, useState } from 'react'
import { buildOverview } from '../../data/overview'
import { tileBlurb } from '../../data/info'
import { ChevronDown, MachineIcon } from '../icons'
import StatTile from '../overview/StatTile'
import Sparkline from '../overview/Sparkline'
import SwarmCanvas from '../overview/SwarmCanvas'
import { useSystemMonitor } from '../overview/useSystemMonitor'
import type { MachineId } from '../overview/useSystemMonitor'
import { useInfo } from '../TileInfoDrawer'

interface OverviewProps {
  accent: string
}

const cardLabelStyle: React.CSSProperties = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
  color: 'var(--text-faint)',
}

const MACHINES: { key: MachineId; label: string }[] = [
  { key: 'studio', label: 'Mac Studio' },
  { key: 'mini', label: 'Mac Mini' },
]

export default function Overview({ accent }: OverviewProps) {
  const ov = useMemo(() => buildOverview(accent), [accent])
  const sys = useSystemMonitor()
  const [sysMenu, setSysMenu] = useState(false)
  const { openInfo } = useInfo()

  return (
    <div className="flex flex-1 flex-col" style={{ minHeight: 0 }}>
      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '22px 26px 40px' }}>
        <div
          style={{ maxWidth: 1180, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16, animation: 'hpanelin 0.4s var(--ease-out)' }}
        >
          {/* Hero header */}
          <div
            className="relative overflow-hidden"
            style={{
              borderRadius: 16,
              padding: '28px 32px',
              background: `linear-gradient(120deg, color-mix(in oklab, ${accent} 13%, transparent) 0%, rgba(155,140,255,0.1) 46%, rgba(45,212,191,0.07) 100%)`,
              border: '1px solid rgba(255,255,255,0.08)',
            }}
          >
            <div style={{ position: 'absolute', width: 280, height: 280, right: -60, top: -120, borderRadius: '50%', background: `radial-gradient(circle, color-mix(in oklab, ${accent} 30%, transparent), transparent 70%)`, pointerEvents: 'none' }} />
            <div style={{ position: 'absolute', width: 240, height: 240, left: -80, bottom: -140, borderRadius: '50%', background: 'radial-gradient(circle, rgba(155,140,255,0.22), transparent 70%)', pointerEvents: 'none' }} />
            <div className="relative flex flex-wrap items-center justify-between" style={{ gap: 24 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.16em', color: accent }}>{ov.eyebrow}</div>
                <h1 style={{ margin: '7px 0 4px', fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 30, letterSpacing: '-0.02em', color: 'var(--text-primary)' }}>{ov.greeting}</h1>
                <p style={{ margin: '0 0 14px', fontSize: 13.5, color: 'var(--text-muted)' }}>{ov.date}</p>
                <div className="flex flex-wrap" style={{ gap: 8 }}>
                  {ov.chips.map((chip) => (
                    <span key={chip.label} className="inline-flex items-center" style={{ gap: 7, fontSize: 11.5, color: '#d4d8e4', background: 'rgba(8,11,17,0.5)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 20, padding: '5px 12px' }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: chip.dot, boxShadow: `0 0 8px ${chip.dot}` }} />
                      {chip.label}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex flex-none" style={{ gap: 12 }}>
                {ov.kpis.map((k) => (
                  <div key={k.lbl} style={{ minWidth: 96, textAlign: 'right', padding: '4px 0' }}>
                    <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 32, lineHeight: 1, background: `linear-gradient(135deg, #fff, color-mix(in oklab, ${accent} 90%, #fff))`, WebkitBackgroundClip: 'text', backgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>{k.val}</div>
                    <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.07em', color: 'var(--text-muted)', marginTop: 5 }}>{k.lbl}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Stat tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
            {ov.stats.map((st) => (
              <StatTile
                key={st.label}
                stat={st}
                onClick={() =>
                  openInfo({
                    category: 'Overview metric',
                    title: st.label,
                    value: st.value,
                    accent: st.accent,
                    desc: tileBlurb(st.label),
                    stats: [
                      { label: 'Current value', value: st.value },
                      { label: 'Tenants', value: 'all' },
                    ],
                    actionLabel: st.sub,
                  })
                }
              />
            ))}
          </div>

          {/* Agent breakdown + activity heatmap (two agent cards) */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 1fr) minmax(360px, 1.3fr)', gap: 16 }}>
            <div
              onClick={() =>
                openInfo({
                  category: 'Overview · Chart',
                  title: 'Agent Breakdown',
                  accent,
                  desc: 'How currently tracked tasks are distributed across the worker fleet. Larger arcs mean an agent is carrying more of the active load.',
                  stats: [
                    { label: 'Total tasks', value: ov.ringTotal },
                    { label: 'Agents', value: String(ov.breakdown.length) },
                    { label: 'Busiest', value: ov.breakdown[0]?.name ?? '—' },
                  ],
                })
              }
              style={{ background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 14, padding: 18, cursor: 'pointer' }}
            >
              <div style={{ ...cardLabelStyle, marginBottom: 14 }}>Agent Breakdown</div>
              <div className="flex flex-wrap items-center" style={{ gap: 18 }}>
                <div style={{ position: 'relative', width: 168, height: 168, flex: 'none' }}>
                  <svg viewBox="0 0 240 240" style={{ width: '100%', height: '100%' }}>
                    <circle cx="120" cy="120" r="100" fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="16" />
                    {ov.ringSegs.map((seg, i) => (
                      <circle key={i} cx="120" cy="120" r="100" fill="none" stroke={seg.color} strokeWidth="16" strokeLinecap="round" strokeDasharray={seg.dash} strokeDashoffset={seg.offset} transform="rotate(-90 120 120)" />
                    ))}
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 30, color: 'var(--text-primary)' }}>{ov.ringTotal}</span>
                    <span style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-faint)' }}>tasks</span>
                  </div>
                </div>
                <div className="flex flex-1 flex-col" style={{ minWidth: 130, gap: 9 }}>
                  {ov.breakdown.map((a) => (
                    <div key={a.key} className="flex items-center" style={{ gap: 9, fontSize: 12 }}>
                      <span className="flex-none" style={{ width: 8, height: 8, borderRadius: '50%', background: a.color, boxShadow: `0 0 9px ${a.color}` }} />
                      <span className="mono flex-1 overflow-hidden text-ellipsis whitespace-nowrap" style={{ minWidth: 0, fontSize: 11.5, color: '#c2c6d6' }}>{a.name}</span>
                      <strong style={{ fontFamily: 'var(--font-display)', color: '#f0f2f8' }}>{a.count}</strong>
                      <em style={{ fontStyle: 'normal', fontSize: 11, color: 'var(--text-faint)', width: 34, textAlign: 'right' }}>{a.pct}%</em>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div
              onClick={() =>
                openInfo({
                  category: 'Overview · Chart',
                  title: 'Agent Activity Heatmap',
                  accent: '#2dd4bf',
                  desc: 'Per-agent activity intensity over the last 24 hours. Brighter cells are hours with more dispatched work.',
                  stats: [
                    { label: 'Window', value: 'Last 24h' },
                    { label: 'Resolution', value: 'Hourly' },
                    { label: 'Peak hour', value: '14:00' },
                  ],
                })
              }
              style={{ background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 14, padding: 18, cursor: 'pointer' }}
            >
              <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
                <div style={cardLabelStyle}>Agent Activity Heatmap</div>
                <span style={{ fontSize: 10.5, color: '#2dd4bf', background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.28)', borderRadius: 6, padding: '2px 8px' }}>Last 24h</span>
              </div>
              <div className="flex flex-col" style={{ gap: 7 }}>
                {ov.heatRows.map((row) => (
                  <div key={row.key} className="flex items-center" style={{ gap: 10 }}>
                    <div className="flex flex-none items-center" style={{ width: 92, gap: 6 }}>
                      <span style={{ color: row.color }}>{row.icon}</span>
                      <b className="mono overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: 10.5, fontWeight: 500, color: '#aeb3c4' }}>{row.name}</b>
                    </div>
                    <div className="flex-1" style={{ display: 'grid', gridTemplateColumns: 'repeat(24, 1fr)', gap: 2 }}>
                      {row.cells.map((c, i) => (
                        <div key={i} style={{ aspectRatio: '1', borderRadius: 2, background: c.bg, animation: `hcellin 0.45s ease backwards`, animationDelay: c.delay }} />
                      ))}
                    </div>
                  </div>
                ))}
                <div className="flex items-center justify-end" style={{ gap: 6, marginTop: 4, fontSize: 10, color: 'var(--text-faint)' }}>
                  <span>Less</span>
                  {['rgba(255,255,255,0.04)', `color-mix(in oklab, ${accent} 26%, transparent)`, `color-mix(in oklab, ${accent} 48%, transparent)`, `color-mix(in oklab, ${accent} 72%, transparent)`, accent].map((bg, i) => (
                    <span key={i} style={{ width: 11, height: 11, borderRadius: 2, background: bg }} />
                  ))}
                  <span>More</span>
                </div>
              </div>
            </div>
          </div>

          {/* System monitor + swarm */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 1.3fr) minmax(300px, 1fr)', gap: 16 }}>
            {/* System monitor */}
            <div className="relative" style={{ background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 14, padding: 18 }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
                <div className="inline-flex items-center" style={{ gap: 8 }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#4ade80', boxShadow: '0 0 7px #4ade80', animation: 'blink 2s ease-in-out infinite' }} />
                  <span style={cardLabelStyle}>System Monitor</span>
                </div>
                <div className="relative">
                  <button
                    onClick={() => setSysMenu((v) => !v)}
                    className="inline-flex items-center"
                    style={{ gap: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 20, padding: '4px 10px', fontSize: 11.5, fontWeight: 600, color: '#c6cad8', fontFamily: 'inherit', cursor: 'pointer' }}
                  >
                    <MachineIcon />
                    {sys.machineLabel}
                    <ChevronDown />
                  </button>
                  {sysMenu && (
                    <div style={{ position: 'absolute', right: 0, top: '100%', marginTop: 6, background: 'var(--s2)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 11, overflow: 'hidden', boxShadow: '0 14px 40px rgba(0,0,0,0.6)', zIndex: 20, minWidth: 140, animation: 'hcmdin 0.15s ease' }}>
                      {MACHINES.map((m) => (
                        <div
                          key={m.key}
                          onClick={() => {
                            sys.setMachine(m.key)
                            setSysMenu(false)
                          }}
                          className="flex items-center"
                          style={{ gap: 8, padding: '9px 12px', fontSize: 12.5, color: '#d4d8e4', cursor: 'pointer', background: m.key === sys.machine ? `color-mix(in oklab, ${accent} 12%, transparent)` : 'transparent' }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
                          onMouseLeave={(e) => (e.currentTarget.style.background = m.key === sys.machine ? `color-mix(in oklab, ${accent} 12%, transparent)` : 'transparent')}
                        >
                          <MachineIcon />
                          {m.label}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                {sys.metrics.map((m) => (
                  <div
                    key={m.key}
                    onClick={() =>
                      openInfo({
                        category: `System monitor · ${sys.machineLabel}`,
                        title: m.label,
                        value: `${m.cur} ${m.unit}`,
                        accent: m.stroke,
                        desc: tileBlurb(m.label),
                        stats: [
                          { label: 'Current', value: `${m.cur} ${m.unit}` },
                          { label: 'Machine', value: sys.machineLabel },
                        ],
                      })
                    }
                    style={{ background: 'rgba(255,255,255,0.025)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 10, padding: '9px 11px 7px', cursor: 'pointer' }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center" style={{ gap: 6, fontSize: 11, color: '#9298ab' }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: m.dot }} />
                        {m.label}
                      </span>
                      <span className="mono" style={{ fontSize: 11.5, color: m.valColor }}>{m.cur} {m.unit}</span>
                    </div>
                    <Sparkline line={m.line} area={m.area} stroke={m.stroke} fill={m.fill} />
                  </div>
                ))}
              </div>

              {/* System memory */}
              <div className="flex items-center" style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--border)', gap: 11 }}>
                <span className="inline-flex flex-none items-center justify-center" style={{ width: 32, height: 32, borderRadius: 9, background: 'rgba(251,111,111,0.12)', border: '1px solid rgba(251,111,111,0.28)', color: '#fb6f6f' }}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                    <rect x="3" y="5" width="18" height="14" rx="2" />
                    <path d="M7 9h.01M7 13h.01" />
                  </svg>
                </span>
                <div className="flex-1" style={{ minWidth: 0 }}>
                  <div className="flex items-center justify-between">
                    <span style={{ fontSize: 12, color: '#c6cad8' }}>System Memory</span>
                    <span className="mono" style={{ fontSize: 12, color: '#e4e6ee' }}>{sys.mem.cur} GB</span>
                  </div>
                  <Sparkline line={sys.mem.line} area={sys.mem.area} stroke="#fb6f6f" fill={sys.mem.fill} height={22} />
                </div>
              </div>

              {/* Per-agent memory */}
              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-faint)', marginBottom: 9 }}>Per-Agent Memory</div>
                <div className="flex flex-col" style={{ gap: 9 }}>
                  {sys.agents.map((a) => (
                    <div key={a.key} className="flex items-center" style={{ gap: 10 }}>
                      <span className="flex-none" style={{ width: 8, height: 8, borderRadius: '50%', background: a.color }} />
                      <div className="flex-1" style={{ minWidth: 0 }}>
                        <div className="flex items-center justify-between">
                          <span style={{ fontSize: 12, color: '#c6cad8' }}>{a.name}</span>
                          <span className="mono" style={{ fontSize: 11.5, color: '#fb6f6f' }}>{a.cur}MB</span>
                        </div>
                        <Sparkline line={a.line} area={a.area} stroke={a.color} fill={a.fill} height={15} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Agent swarm */}
            <div
              onClick={() =>
                openInfo({
                  category: 'Overview · Live',
                  title: 'Agent Swarm',
                  accent: '#9b8cff',
                  desc: 'A live particle field visualizing emergent coordination between agents. Denser clusters indicate agents collaborating on related tasks.',
                  stats: [
                    { label: 'Mode', value: 'Emergent' },
                    { label: 'Agents', value: '5' },
                  ],
                })
              }
              className="relative overflow-hidden"
              style={{ background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 14, minHeight: 286, cursor: 'pointer' }}
            >
              <SwarmCanvas accent={accent} />
              <div className="relative flex items-center justify-between" style={{ zIndex: 1, padding: 18 }}>
                <div className="inline-flex items-center" style={{ gap: 8 }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: accent, boxShadow: `0 0 7px ${accent}`, animation: 'hpulse 1.6s ease-in-out infinite' }} />
                  <span style={cardLabelStyle}>Agent Swarm</span>
                </div>
                <span style={{ fontSize: 10.5, color: '#9b8cff', background: 'rgba(155,140,255,0.1)', border: '1px solid rgba(155,140,255,0.28)', borderRadius: 6, padding: '2px 8px' }}>emergent</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
