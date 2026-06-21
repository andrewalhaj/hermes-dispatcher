import { useMemo } from 'react'
import { ACCENT } from '../../data/agents'
import { buildInsights } from '../../data/phase3'
import { useInfo } from '../TileInfoDrawer'
import '../../styles/phase3.css'

interface InsightsProps {
  accent?: string
}

const cardLabel: React.CSSProperties = { fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6a7088' }
const cardBase: React.CSSProperties = {
  background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 14, padding: 18,
  transition: 'transform 0.28s cubic-bezier(0.16,1,0.3,1), border-color 0.28s, box-shadow 0.28s', cursor: 'pointer',
}

function hoverIn(e: React.MouseEvent<HTMLElement>) {
  e.currentTarget.style.transform = 'translateY(-4px)'
  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)'
  e.currentTarget.style.boxShadow = '0 14px 34px rgba(0,0,0,0.45)'
}
function hoverOut(e: React.MouseEvent<HTMLElement>) {
  e.currentTarget.style.transform = 'none'
  e.currentTarget.style.borderColor = 'var(--border)'
  e.currentTarget.style.boxShadow = 'none'
}

export default function Insights({ accent = ACCENT }: InsightsProps) {
  const ins = useMemo(() => buildInsights(accent), [accent])
  const { openInfo } = useInfo()
  const open = openInfo

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header className="flex items-center justify-between" style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Usage Analytics</div>
          <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>{ins.period}</div>
        </div>
        <span className="inline-flex items-center" style={{ gap: 6, fontSize: 12, color: '#c6cad8', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 20, padding: '5px 12px' }}>
          {ins.period}
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#9298ab" strokeWidth={2} aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
        </span>
      </header>
      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '22px 26px 40px' }}>
        <div style={{ maxWidth: 1080, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16, animation: 'hpanelin 0.4s var(--ease-out)' }}>
          {/* KPI tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
            {ins.kpis.map((k) => (
              <button
                key={k.label}
                onClick={() => open(k.info)}
                className="relative overflow-hidden text-left"
                style={{ background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 13, padding: '16px 17px', cursor: 'pointer', transition: 'transform 0.25s, border-color 0.25s, box-shadow 0.25s' }}
                onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-3px)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)'; e.currentTarget.style.boxShadow = '0 12px 30px rgba(0,0,0,0.42)' }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = 'none' }}
              >
                <span style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 2, background: k.accent }} />
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 26, color: 'var(--text-primary)' }}>{k.value}</div>
                <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088', marginTop: 5 }}>{k.label}</div>
              </button>
            ))}
          </div>

          {/* Activity by Day + Token Breakdown */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr)', gap: 16 }}>
            <div style={cardBase} onClick={() => open(ins.activityInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
              <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
                <div style={cardLabel}>Activity by Day</div>
                <span style={{ fontSize: 10.5, color: '#2dd4bf', background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.28)', borderRadius: 6, padding: '2px 8px' }}>Peak {ins.peak}</span>
              </div>
              <div className="flex items-end" style={{ gap: 5, height: 96 }}>
                {ins.days.map((d, i) => (
                  <div key={i} style={{ flex: 1, minWidth: 0, height: d.h, borderRadius: '3px 3px 0 0', background: d.bg }} />
                ))}
              </div>
            </div>
            <div style={cardBase} onClick={() => open(ins.tokenInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
              <div style={{ ...cardLabel, marginBottom: 16 }}>Token Breakdown</div>
              <div className="flex items-baseline" style={{ gap: 8, marginBottom: 14 }}>
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 26, color: 'var(--text-primary)' }}>{ins.tokTotal}</span>
                <span style={{ fontSize: 11.5, color: '#6a7088' }}>total tokens</span>
              </div>
              <div className="flex" style={{ height: 10, borderRadius: 99, overflow: 'hidden', background: 'rgba(255,255,255,0.05)' }}>
                <div style={{ width: ins.tokInPct, background: 'var(--ac)' }} />
                <div style={{ width: ins.tokOutPct, background: '#5aa2f0' }} />
              </div>
              <div className="flex justify-between" style={{ marginTop: 11, fontSize: 12 }}>
                <span className="inline-flex items-center" style={{ gap: 6, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--ac)' }} />Input <b style={{ color: '#d4d8e4', fontWeight: 600 }}>{ins.tokIn}</b>
                </span>
                <span className="inline-flex items-center" style={{ gap: 6, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: '#5aa2f0' }} />Output <b style={{ color: '#d4d8e4', fontWeight: 600 }}>{ins.tokOut}</b>
                </span>
              </div>
            </div>
          </div>

          {/* Models table */}
          <div style={cardBase} onClick={() => open(ins.modelsInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
            <div style={{ ...cardLabel, marginBottom: 14 }}>Models</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 96px 88px 70px', gap: 10, padding: '0 4px 8px', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#565d72' }}>
              <span>Model</span><span>Sessions</span><span>Tokens</span><span>Cost</span><span>Share</span>
            </div>
            <div className="flex flex-col" style={{ gap: 4 }}>
              {ins.models.map((m) => (
                <div key={m.name} style={{ display: 'grid', gridTemplateColumns: '1fr 80px 96px 88px 70px', gap: 10, alignItems: 'center', padding: '9px 4px', borderTop: '1px solid rgba(255,255,255,0.05)', fontSize: 12.5 }}>
                  <span className="inline-flex items-center" style={{ gap: 8, color: '#e4e6ee', minWidth: 0 }}>
                    <span className="flex-none" style={{ width: 8, height: 8, borderRadius: '50%', background: m.color, boxShadow: `0 0 7px ${m.color}` }} />
                    <span className="overflow-hidden text-ellipsis whitespace-nowrap">{m.name}</span>
                  </span>
                  <span className="mono" style={{ color: 'var(--text-muted)' }}>{m.sessions}</span>
                  <span className="mono" style={{ color: 'var(--text-muted)' }}>{m.tokens}</span>
                  <span className="mono" style={{ color: '#d4d8e4' }}>{m.cost}</span>
                  <span className="mono" style={{ color: m.color }}>{m.share}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Skill usage */}
          <div style={cardBase} onClick={() => open(ins.skillsInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
            <div style={{ ...cardLabel, marginBottom: 14 }}>Skill Usage</div>
            <div className="flex flex-col" style={{ gap: 11 }}>
              {ins.skills.map((sk) => (
                <div key={sk.skill} className="flex items-center" style={{ gap: 12 }}>
                  <span className="mono flex-none" style={{ width: 92, fontSize: 12, color: '#c6cad8' }}>{sk.skill}</span>
                  <div className="flex-1" style={{ height: 7, borderRadius: 99, background: 'rgba(255,255,255,0.05)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: sk.w, borderRadius: 99, background: 'linear-gradient(90deg, color-mix(in oklab, var(--ac) 60%, transparent), var(--ac))' }} />
                  </div>
                  <span className="mono flex-none" style={{ width: 40, textAlign: 'right', fontSize: 11.5, color: 'var(--text-muted)' }}>{sk.uses}</span>
                  <span className="mono flex-none" style={{ width: 40, textAlign: 'right', fontSize: 11, color: '#565d72' }}>{sk.share}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
