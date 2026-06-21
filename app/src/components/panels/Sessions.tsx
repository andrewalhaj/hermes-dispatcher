import { useMemo, useState } from 'react'
import { ACCENT } from '../../data/agents'
import { buildSessions } from '../../data/phase3'
import type { SessionRow } from '../../data/phase3'
import '../../styles/phase3.css'

interface SessionsProps {
  accent?: string
  onOpenSession?: (id: string) => void
}

type Filter = 'all' | SessionRow['status']

export default function Sessions({ accent = ACCENT, onOpenSession }: SessionsProps) {
  const { sessions, summary, statuses, statusMeta } = useMemo(() => buildSessions(), [])
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return sessions.filter(
      (x) =>
        (filter === 'all' || x.statusKey === filter) &&
        (!q || (x.title + ' ' + x.worker + ' ' + x.tenant).toLowerCase().includes(q)),
    )
  }, [sessions, filter, query])

  const pills: { key: Filter; label: string; color: string }[] = [
    { key: 'all', label: 'All', color: accent },
    ...statuses.map((s) => ({ key: s as Filter, label: statusMeta[s].l, color: statusMeta[s].c })),
  ]

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header className="flex items-center justify-between" style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Sessions</div>
          <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>live agent runs across all tenants</div>
        </div>
        <div className="flex" style={{ gap: 8 }}>
          <span className="inline-flex items-center" style={{ gap: 6, fontSize: 12, color: '#2dd4bf', background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.28)', borderRadius: 8, padding: '6px 11px' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#2dd4bf', animation: 'hpulse 1.6s ease-in-out infinite' }} />{summary.running} running
          </span>
          <span style={{ fontSize: 12, color: '#5aa2f0', background: 'rgba(90,162,240,0.1)', border: '1px solid rgba(90,162,240,0.28)', borderRadius: 8, padding: '6px 11px' }}>{summary.idle} idle</span>
          <span style={{ fontSize: 12, color: '#fb6f6f', background: 'rgba(251,111,111,0.1)', border: '1px solid rgba(251,111,111,0.28)', borderRadius: 8, padding: '6px 11px' }}>{summary.error} error</span>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '20px 26px 32px' }}>
        <div style={{ maxWidth: 1080, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 14, animation: 'hpanelin 0.4s var(--ease-out)' }}>
          {/* Filter bar */}
          <div className="flex flex-wrap items-center" style={{ gap: 8 }}>
            <div className="relative" style={{ flex: '1 1 280px', minWidth: 200 }}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#666c82" strokeWidth={2} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} aria-hidden="true">
                <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
              </svg>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter sessions by task, worker or tenant…"
                style={{ width: '100%', background: 'rgba(17,21,31,0.55)', border: '1px solid rgba(255,255,255,0.09)', borderRadius: 9, padding: '9px 12px 9px 34px', color: '#e9ebf2', fontSize: 13, fontFamily: 'inherit', outline: 'none' }}
                onFocus={(e) => (e.currentTarget.style.borderColor = accent)}
                onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.09)')}
              />
            </div>
            <div className="flex flex-wrap" style={{ gap: 6 }}>
              {pills.map((p) => {
                const on = filter === p.key
                return (
                  <button
                    key={p.key}
                    onClick={() => setFilter(p.key)}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', padding: '7px 12px', borderRadius: 20, background: on ? `color-mix(in oklab, ${p.color} 14%, transparent)` : 'transparent', border: `1px solid ${on ? `color-mix(in oklab, ${p.color} 40%, transparent)` : 'rgba(255,255,255,0.1)'}`, color: on ? p.color : '#9298ab', transition: 'all 0.15s' }}
                  >
                    {p.key !== 'all' && <span style={{ width: 7, height: 7, borderRadius: '50%', background: p.color }} />}
                    {p.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Header row */}
          <div style={{ display: 'grid', gridTemplateColumns: '44px 1fr 150px 96px 96px 84px', gap: 12, padding: '0 16px 4px', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#565d72' }}>
            <span>Run</span><span>Session</span><span>Agent</span><span>Status</span><span>Updated</span><span>Msgs</span>
          </div>

          {/* Rows */}
          <div className="flex flex-col" style={{ gap: 10 }}>
            {rows.map((x) => (
              <button
                key={x.id}
                onClick={() => onOpenSession?.(x.id)}
                className="text-left"
                style={{ display: 'grid', gridTemplateColumns: '44px 1fr 150px 96px 96px 84px', gap: 12, alignItems: 'center', background: 'var(--s3)', border: '1px solid var(--border)', borderLeft: `3px solid ${x.statusColor}`, borderRadius: 10, padding: '13px 16px', cursor: 'pointer', transition: 'border-color 0.15s, background 0.15s' }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.18)'; e.currentTarget.style.borderLeftColor = x.statusColor; e.currentTarget.style.background = 'var(--s4)' }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.borderLeftColor = x.statusColor; e.currentTarget.style.background = 'var(--s3)' }}
              >
                <span className="inline-flex items-center justify-center" style={{ width: 28, height: 28, borderRadius: 8, fontSize: 14, color: x.statusColor, background: `color-mix(in oklab, ${x.statusColor} 14%, transparent)` }}>{x.icon}</span>
                <span style={{ minWidth: 0 }}>
                  <span className="block overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: 13, color: '#e4e6ee' }}>{x.title}</span>
                  <span className="mono block" style={{ fontSize: 10.5, color: '#565d72', marginTop: 2 }}>#{x.id} · {x.tenant}</span>
                </span>
                <span className="mono overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{x.worker}</span>
                <span className="inline-flex items-center" style={{ gap: 6, fontSize: 11, color: x.statusColor }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: x.statusColor }} />{x.statusLabel}
                </span>
                <span className="mono" style={{ fontSize: 11.5, color: '#9298ab' }}>{x.age} ago</span>
                <span className="mono" style={{ fontSize: 11.5, color: '#9298ab' }}>{x.tokens}</span>
              </button>
            ))}
            {rows.length === 0 && (
              <div style={{ padding: 48, textAlign: 'center', fontSize: 13, color: '#565d72' }}>No sessions match your filters.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
