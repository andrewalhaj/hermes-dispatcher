import { useEffect, useRef, useState } from 'react'
import { ACCENT } from '../../data/agents'
import '../../styles/phase3.css'

interface LogsProps {
  accent?: string
}

type LogSource = 'hermes' | 'kanban' | 'system'

const ANSI_RE = /\x1b\[[0-9;]*[mABCDEFGHJKLMSTfhilmnprsu]/g

function stripAnsi(s: string): string {
  return s.replace(ANSI_RE, '')
}

const SOURCES: { key: LogSource; label: string }[] = [
  { key: 'hermes', label: 'Hermes' },
  { key: 'kanban', label: 'Kanban' },
  { key: 'system', label: 'System' },
]

export default function Logs({ accent = ACCENT }: LogsProps) {
  const [source, setSource] = useState<LogSource>('hermes')
  const [lines, setLines] = useState<string[]>([])
  const [live, setLive] = useState(false)
  const [loading, setLoading] = useState(false)
  const esRef = useRef<EventSource | null>(null)
  const preRef = useRef<HTMLPreElement | null>(null)

  function scrollBottom() {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight
  }

  // Fetch initial batch whenever source changes
  useEffect(() => {
    closeSse()
    setLive(false)
    setLines([])
    setLoading(true)
    fetch(`/api/logs?source=${source}&lines=200`)
      .then((r) => r.json())
      .then((data: { lines: string[] }) => {
        setLines(data.lines.map(stripAnsi))
        setLoading(false)
        setTimeout(scrollBottom, 0)
      })
      .catch(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source])

  // Auto-scroll when lines change
  useEffect(() => {
    scrollBottom()
  }, [lines])

  function closeSse() {
    if (esRef.current) {
      esRef.current.close()
      esRef.current = null
    }
  }

  function openSse() {
    closeSse()
    const es = new EventSource(`/api/logs/stream?source=${source}`)
    es.onmessage = (e) => {
      try {
        const { line } = JSON.parse(e.data) as { line: string }
        setLines((prev) => [...prev, stripAnsi(line)])
      } catch {
        // ignore malformed events
      }
    }
    esRef.current = es
  }

  function toggleLive() {
    if (live) {
      closeSse()
      setLive(false)
    } else {
      openSse()
      setLive(true)
    }
  }

  // Close SSE on unmount
  useEffect(() => () => closeSse(), [])

  function handleSourceSwitch(s: LogSource) {
    closeSse()
    setLive(false)
    setSource(s)
  }

  function handleClear() {
    setLines([])
  }

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      {/* Header */}
      <div style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="flex items-center justify-between">
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Logs</div>
            <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>
              {loading ? 'Loading…' : `${lines.length} lines`}
              {live && <span style={{ marginLeft: 8, color: accent }}>● live</span>}
            </div>
          </div>
          <div className="flex items-center" style={{ gap: 8 }}>
            {/* Clear */}
            <button
              onClick={handleClear}
              style={{ fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', padding: '7px 12px', borderRadius: 8, background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', color: '#9298ab', transition: 'all 0.15s' }}
            >
              Clear
            </button>
            {/* Live toggle */}
            <button
              onClick={toggleLive}
              className="inline-flex items-center"
              style={{ gap: 7, fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', padding: '7px 12px', borderRadius: 8, background: live ? `color-mix(in oklab, ${accent} 14%, transparent)` : 'transparent', border: `1px solid ${live ? `color-mix(in oklab, ${accent} 40%, transparent)` : 'rgba(255,255,255,0.1)'}`, color: live ? accent : '#9298ab', transition: 'all 0.15s' }}
            >
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: live ? accent : '#6a7088', boxShadow: live ? `0 0 6px ${accent}` : 'none', transition: 'all 0.15s' }} />
              {live ? 'Live on' : 'Live off'}
            </button>
          </div>
        </div>

        {/* Source tabs */}
        <div className="flex" style={{ gap: 6 }}>
          {SOURCES.map(({ key, label }) => {
            const active = source === key
            return (
              <button
                key={key}
                onClick={() => handleSourceSwitch(key)}
                style={{ fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', padding: '6px 14px', borderRadius: 8, background: active ? `color-mix(in oklab, ${accent} 14%, transparent)` : 'transparent', border: `1px solid ${active ? `color-mix(in oklab, ${accent} 40%, transparent)` : 'rgba(255,255,255,0.1)'}`, color: active ? accent : '#9298ab', fontWeight: active ? 600 : 400, transition: 'all 0.15s' }}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Log output */}
      <pre
        ref={preRef}
        className="flex-1 overflow-y-auto"
        style={{ minHeight: 0, margin: 0, padding: '16px 24px', fontFamily: "'IBM Plex Mono', 'Fira Code', monospace", fontSize: 12, lineHeight: 1.7, color: '#c8cfe0', background: 'transparent', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}
      >
        {lines.length === 0 && !loading && (
          <span style={{ color: '#565d72' }}>No log data for {source}.</span>
        )}
        {lines.map((line, i) => (
          <div key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.02)', paddingBottom: 1 }}>
            {line || ' '}
          </div>
        ))}
      </pre>
    </div>
  )
}
