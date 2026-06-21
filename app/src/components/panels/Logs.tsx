import { useEffect, useMemo, useRef, useState } from 'react'
import { ACCENT } from '../../data/agents'
import { LOGS, LOG_LEVELS, logLevelStyle, logStatusColor } from '../../data/phase3'
import type { LogLevel } from '../../data/phase3'
import '../../styles/phase3.css'

interface LogsProps {
  accent?: string
}

function fmtTime(ts: string): string {
  return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function Logs({ accent = ACCENT }: LogsProps) {
  const [query, setQuery] = useState('')
  const [levels, setLevels] = useState<LogLevel[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const listRef = useRef<HTMLDivElement | null>(null)

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return LOGS.filter(
      (l) => (!q || (l.message + ' ' + l.service).toLowerCase().includes(q)) && (levels.length === 0 || levels.includes(l.level)),
    )
  }, [query, levels])

  // Auto-scroll to bottom when enabled and the filtered set changes.
  useEffect(() => {
    if (autoScroll && listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [rows, autoScroll])

  const toggleLevel = (l: LogLevel) => setLevels((cur) => (cur.includes(l) ? cur.filter((x) => x !== l) : [...cur, l]))

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <div style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column', gap: 13 }}>
        <div className="flex items-center justify-between">
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Logs</div>
            <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>{rows.length} of {LOGS.length} events</div>
          </div>
          <button
            onClick={() => setAutoScroll((v) => !v)}
            className="inline-flex items-center"
            style={{ gap: 7, fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', padding: '7px 12px', borderRadius: 8, background: autoScroll ? `color-mix(in oklab, ${accent} 14%, transparent)` : 'transparent', border: `1px solid ${autoScroll ? `color-mix(in oklab, ${accent} 40%, transparent)` : 'rgba(255,255,255,0.1)'}`, color: autoScroll ? accent : '#9298ab', transition: 'all 0.15s' }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true"><path d="M12 5v14M19 12l-7 7-7-7" /></svg>
            Auto-scroll {autoScroll ? 'on' : 'off'}
          </button>
        </div>
        <div className="flex" style={{ gap: 8 }}>
          <div className="relative" style={{ flex: 1 }}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#666c82" strokeWidth={2} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} aria-hidden="true">
              <circle cx="11" cy="11" r="7" /><path d="M21 21l-4.3-4.3" />
            </svg>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search logs by message or service…"
              style={{ width: '100%', background: 'rgba(17,21,31,0.55)', border: '1px solid rgba(255,255,255,0.09)', borderRadius: 9, padding: '9px 12px 9px 34px', color: '#e9ebf2', fontSize: 13, fontFamily: 'inherit', outline: 'none' }}
              onFocus={(e) => (e.currentTarget.style.borderColor = accent)}
              onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.09)')}
            />
          </div>
          {/* Level filter pills */}
          <div className="flex" style={{ gap: 6 }}>
            {LOG_LEVELS.map((l) => {
              const on = levels.includes(l)
              const ls = logLevelStyle(l)
              return (
                <button
                  key={l}
                  onClick={() => toggleLevel(l)}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', textTransform: 'capitalize', padding: '8px 12px', borderRadius: 8, background: on ? ls.bg : 'transparent', border: `1px solid ${on ? ls.c : 'rgba(255,255,255,0.1)'}`, color: on ? ls.c : '#9298ab', transition: 'all 0.15s' }}
                >
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: ls.c }} />
                  {l}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto" style={{ minHeight: 0 }}>
        {rows.map((l) => {
          const ls = logLevelStyle(l.level)
          const isOpen = expanded === l.id
          return (
            <div key={l.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
              <button
                onClick={() => setExpanded((x) => (x === l.id ? null : l.id))}
                className="flex w-full items-center text-left"
                style={{ gap: 13, padding: '12px 24px', background: 'none', border: 'none', fontFamily: 'inherit', cursor: 'pointer' }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.025)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#6a7088" strokeWidth={2} className="flex-none" style={{ transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.18s' }} aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
                <span className="flex-none" style={{ fontSize: 10, fontWeight: 600, textTransform: 'capitalize', padding: '2px 8px', borderRadius: 6, background: ls.bg, color: ls.c }}>{l.level}</span>
                <span className="mono flex-none" style={{ width: 84, fontSize: 11, color: '#6a7088' }}>{fmtTime(l.ts)}</span>
                <span className="flex-none" style={{ fontSize: 12.5, fontWeight: 500, color: '#d4d8e4' }}>{l.service}</span>
                <span className="flex-1 overflow-hidden text-ellipsis whitespace-nowrap" style={{ minWidth: 0, fontSize: 12.5, color: 'var(--text-muted)' }}>{l.message}</span>
                <span className="mono flex-none" style={{ fontSize: 12, fontWeight: 600, color: logStatusColor(l.status) }}>{l.status}</span>
                <span className="mono flex-none" style={{ width: 48, textAlign: 'right', fontSize: 11, color: '#6a7088' }}>{l.duration}</span>
              </button>
              {isOpen && (
                <div style={{ padding: '4px 24px 18px 50px', display: 'flex', flexDirection: 'column', gap: 13, background: 'rgba(255,255,255,0.015)' }}>
                  <div>
                    <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088', marginBottom: 6 }}>Message</div>
                    <div className="mono" style={{ fontSize: 12.5, color: '#d4d8e4', background: 'rgba(8,11,17,0.5)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>{l.message}</div>
                  </div>
                  <div className="flex" style={{ gap: 36 }}>
                    <div>
                      <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088', marginBottom: 4 }}>Duration</div>
                      <div className="mono" style={{ fontSize: 12.5, color: '#d4d8e4' }}>{l.duration}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088', marginBottom: 4 }}>Timestamp</div>
                      <div className="mono" style={{ fontSize: 11.5, color: '#d4d8e4' }}>{l.ts}</div>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088', marginBottom: 7 }}>Tags</div>
                    <div className="flex flex-wrap" style={{ gap: 6 }}>
                      {l.tags.map((t) => (
                        <span key={t} className="mono" style={{ fontSize: 10.5, color: '#9298ab', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 6, padding: '2px 8px' }}>{t}</span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })}
        {rows.length === 0 && <div style={{ padding: 48, textAlign: 'center', fontSize: 13, color: '#565d72' }}>No logs match your filters.</div>}
      </div>
    </div>
  )
}
