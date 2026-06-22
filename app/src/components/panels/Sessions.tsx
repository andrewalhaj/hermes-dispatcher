import { useEffect, useMemo, useRef, useState } from 'react'
import { ACCENT } from '../../data/agents'
import '../../styles/phase3.css'

interface SessionsProps {
  accent?: string
  onOpenSession?: (id: string) => void
}

interface ApiSession {
  id: string
  title: string
  profile: string
  created_at: number
  updated_at: number
  source: string
  message_count: number
}

interface ApiMessage {
  role: string
  content: string
  created_at: number
}

const SOURCE_COLOR: Record<string, string> = {
  telegram: '#5aa2f0',
  cli: '#f6b73c',
  webui: '#2dd4bf',
  tui: '#4ade80',
  discord: '#9b8cff',
  cron: '#6a7088',
  subagent: '#6a7088',
}

const INTERACTIVE_SOURCES = new Set(['telegram', 'cli', 'tui', 'webui', 'discord'])

function srcColor(source: string): string {
  return SOURCE_COLOR[source] ?? '#6a7088'
}

function srcLabel(source: string): string {
  return source.charAt(0).toUpperCase() + source.slice(1)
}

function fmtAge(epochSec: number): string {
  const diff = Math.max(0, Date.now() / 1000 - epochSec)
  if (diff < 60) return Math.round(diff) + 's'
  if (diff < 3600) return Math.round(diff / 60) + 'm'
  if (diff < 86400) return Math.round(diff / 3600) + 'h'
  return Math.round(diff / 86400) + 'd'
}

function roleColor(role: string): string {
  if (role === 'user') return '#5aa2f0'
  if (role === 'assistant') return '#2dd4bf'
  if (role === 'tool') return '#9b8cff'
  return '#6a7088'
}

export default function Sessions({ accent = ACCENT, onOpenSession }: SessionsProps) {
  const [sessions, setSessions] = useState<ApiSession[]>([])
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [filterSource, setFilterSource] = useState<string>('all')
  const [drawerSession, setDrawerSession] = useState<ApiSession | null>(null)
  const [messages, setMessages] = useState<ApiMessage[]>([])
  const [msgsLoading, setMsgsLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Load sessions (debounced on query, immediate on empty)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = query.trim()
    const delay = q ? 300 : 0
    debounceRef.current = setTimeout(() => {
      setLoading(true)
      const url = q
        ? `/api/sessions/search?q=${encodeURIComponent(q)}`
        : '/api/sessions'
      fetch(url)
        .then((r) => r.json())
        .then((data: ApiSession[]) => { setSessions(data); setLoading(false) })
        .catch(() => setLoading(false))
    }, delay)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [query])

  // Client-side filter by source
  const rows = useMemo(() => {
    if (filterSource === 'all') return sessions
    return sessions.filter((s) => s.source === filterSource)
  }, [sessions, filterSource])

  // Unique sources from loaded data (for filter pills)
  const sources = useMemo(() => {
    const seen = new Set<string>()
    sessions.forEach((s) => seen.add(s.source))
    return Array.from(seen).sort()
  }, [sessions])

  const summary = useMemo(() => ({
    interactive: sessions.filter((s) => INTERACTIVE_SOURCES.has(s.source)).length,
    automated: sessions.filter((s) => !INTERACTIVE_SOURCES.has(s.source)).length,
  }), [sessions])

  function openDrawer(session: ApiSession) {
    onOpenSession?.(session.id)
    setDrawerSession(session)
    setMessages([])
    setMsgsLoading(true)
    fetch(`/api/sessions/${session.id}/messages`)
      .then((r) => r.json())
      .then((data: ApiMessage[]) => { setMessages(data); setMsgsLoading(false) })
      .catch(() => setMsgsLoading(false))
  }

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      {/* Header */}
      <header className="flex items-center justify-between" style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Sessions</div>
          <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>live agent runs across all sources</div>
        </div>
        <div className="flex" style={{ gap: 8 }}>
          <span className="inline-flex items-center" style={{ gap: 6, fontSize: 12, color: '#2dd4bf', background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.28)', borderRadius: 8, padding: '6px 11px' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#2dd4bf', animation: 'hpulse 1.6s ease-in-out infinite' }} />{summary.interactive} interactive
          </span>
          <span style={{ fontSize: 12, color: '#5aa2f0', background: 'rgba(90,162,240,0.1)', border: '1px solid rgba(90,162,240,0.28)', borderRadius: 8, padding: '6px 11px' }}>{summary.automated} automated</span>
          <span style={{ fontSize: 12, color: '#9298ab', background: 'rgba(106,112,136,0.1)', border: '1px solid rgba(106,112,136,0.28)', borderRadius: 8, padding: '6px 11px' }}>{sessions.length} total</span>
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
                placeholder="Search sessions by title or message content…"
                style={{ width: '100%', background: 'rgba(17,21,31,0.55)', border: '1px solid rgba(255,255,255,0.09)', borderRadius: 9, padding: '9px 12px 9px 34px', color: '#e9ebf2', fontSize: 13, fontFamily: 'inherit', outline: 'none' }}
                onFocus={(e) => (e.currentTarget.style.borderColor = accent)}
                onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.09)')}
              />
            </div>
            <div className="flex flex-wrap" style={{ gap: 6 }}>
              {(['all', ...sources] as string[]).map((src) => {
                const on = filterSource === src
                const color = src === 'all' ? accent : srcColor(src)
                return (
                  <button
                    key={src}
                    onClick={() => setFilterSource(src)}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', padding: '7px 12px', borderRadius: 20, background: on ? `color-mix(in oklab, ${color} 14%, transparent)` : 'transparent', border: `1px solid ${on ? `color-mix(in oklab, ${color} 40%, transparent)` : 'rgba(255,255,255,0.1)'}`, color: on ? color : '#9298ab', transition: 'all 0.15s' }}
                  >
                    {src !== 'all' && <span style={{ width: 7, height: 7, borderRadius: '50%', background: color }} />}
                    {src === 'all' ? 'All' : srcLabel(src)}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Header row */}
          <div style={{ display: 'grid', gridTemplateColumns: '44px 1fr 150px 96px 96px 64px', gap: 12, padding: '0 16px 4px', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#565d72' }}>
            <span>Src</span><span>Session</span><span>Profile</span><span>Source</span><span>Updated</span><span>Msgs</span>
          </div>

          {/* Session rows */}
          {loading ? (
            <div style={{ padding: 48, textAlign: 'center', fontSize: 13, color: '#565d72' }}>Loading sessions…</div>
          ) : (
            <div className="flex flex-col" style={{ gap: 10 }}>
              {rows.map((x) => {
                const color = srcColor(x.source)
                return (
                  <button
                    key={x.id}
                    onClick={() => openDrawer(x)}
                    className="text-left"
                    style={{ display: 'grid', gridTemplateColumns: '44px 1fr 150px 96px 96px 64px', gap: 12, alignItems: 'center', background: 'var(--s3)', border: '1px solid var(--border)', borderLeft: `3px solid ${color}`, borderRadius: 10, padding: '13px 16px', cursor: 'pointer', transition: 'border-color 0.15s, background 0.15s' }}
                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.18)'; e.currentTarget.style.borderLeftColor = color; e.currentTarget.style.background = 'var(--s4)' }}
                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.borderLeftColor = color; e.currentTarget.style.background = 'var(--s3)' }}
                  >
                    <span className="inline-flex items-center justify-center" style={{ width: 28, height: 28, borderRadius: 8, fontSize: 10, fontWeight: 700, letterSpacing: '0.04em', color, background: `color-mix(in oklab, ${color} 14%, transparent)`, fontFamily: 'var(--font-mono)' }}>
                      {x.source.slice(0, 3).toUpperCase()}
                    </span>
                    <span style={{ minWidth: 0 }}>
                      <span className="block overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: 13, color: '#e4e6ee' }}>{x.title}</span>
                      <span className="mono block overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: 10.5, color: '#565d72', marginTop: 2 }}>#{x.id.slice(0, 18)} · {x.profile}</span>
                    </span>
                    <span className="mono overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>{x.profile}</span>
                    <span className="inline-flex items-center" style={{ gap: 6, fontSize: 11, color }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color }} />{srcLabel(x.source)}
                    </span>
                    <span className="mono" style={{ fontSize: 11.5, color: '#9298ab' }}>{fmtAge(x.updated_at)} ago</span>
                    <span className="mono" style={{ fontSize: 11.5, color: '#9298ab' }}>{x.message_count}</span>
                  </button>
                )
              })}
              {rows.length === 0 && (
                <div style={{ padding: 48, textAlign: 'center', fontSize: 13, color: '#565d72' }}>No sessions match your filters.</div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Messages slide-over drawer */}
      {drawerSession && (
        <>
          {/* Backdrop */}
          <div
            onClick={() => setDrawerSession(null)}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 200 }}
          />
          {/* Drawer panel */}
          <div style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 500, maxWidth: '92vw', background: 'var(--bg, #0d1017)', borderLeft: '1px solid rgba(255,255,255,0.09)', zIndex: 201, display: 'flex', flexDirection: 'column', boxShadow: '-12px 0 48px rgba(0,0,0,0.5)', animation: 'hpanelin 0.25s var(--ease-out)' }}>
            {/* Drawer header */}
            <div style={{ padding: '18px 20px', borderBottom: '1px solid rgba(255,255,255,0.07)', display: 'flex', alignItems: 'flex-start', gap: 12, flexShrink: 0 }}>
              <span style={{ width: 32, height: 32, borderRadius: 9, fontSize: 10, fontWeight: 700, letterSpacing: '0.04em', color: srcColor(drawerSession.source), background: `color-mix(in oklab, ${srcColor(drawerSession.source)} 14%, transparent)`, fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {drawerSession.source.slice(0, 3).toUpperCase()}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: '#e4e6ee', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{drawerSession.title}</div>
                <div style={{ fontSize: 11, color: '#565d72', marginTop: 3 }}>
                  {drawerSession.profile} · {srcLabel(drawerSession.source)} · {drawerSession.message_count} msgs
                </div>
              </div>
              <button
                onClick={() => setDrawerSession(null)}
                style={{ flexShrink: 0, width: 30, height: 30, borderRadius: 8, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.05)', color: '#9298ab', fontSize: 18, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', lineHeight: 1 }}
              >×</button>
            </div>

            {/* Message list */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              {msgsLoading && (
                <div style={{ textAlign: 'center', color: '#565d72', fontSize: 13, paddingTop: 40 }}>Loading messages…</div>
              )}
              {!msgsLoading && messages.length === 0 && (
                <div style={{ textAlign: 'center', color: '#565d72', fontSize: 13, paddingTop: 40 }}>No messages found.</div>
              )}
              {messages.map((msg, i) => {
                const color = roleColor(msg.role)
                const isTool = msg.role === 'tool'
                const isSystem = msg.role === 'system'
                return (
                  <div key={i}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                      <span style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700, color, fontFamily: 'var(--font-mono)' }}>{msg.role}</span>
                      <span style={{ fontSize: 10, color: '#3d4259' }}>{fmtAge(msg.created_at)} ago</span>
                    </div>
                    <div style={{
                      fontSize: 12,
                      color: isTool ? '#b8abff' : isSystem ? '#7a8099' : '#c8cad6',
                      background: isTool ? 'rgba(155,140,255,0.08)' : isSystem ? 'rgba(255,255,255,0.02)' : 'rgba(255,255,255,0.03)',
                      borderRadius: 8,
                      padding: '9px 12px',
                      fontFamily: isTool ? 'var(--font-mono)' : 'inherit',
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      maxHeight: 220,
                      overflowY: 'auto',
                      border: isTool ? '1px solid rgba(155,140,255,0.18)' : '1px solid rgba(255,255,255,0.04)',
                      lineHeight: 1.55,
                    }}>
                      {(() => { const c = msg.content ?? ''; return c.length > 1400 ? c.slice(0, 1400) + '…' : c })()}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
