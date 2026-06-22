import { useEffect, useRef, useState } from 'react'
import { ACCENT } from '../../data/agents'
import '../../styles/phase3.css'

interface LogsProps {
  accent?: string
}

type LogSource = 'hermes' | 'kanban' | 'system'
type LogLevel = 'debug' | 'info' | 'warn' | 'error'

interface LogEntry {
  id: string
  timestamp: string
  service: string
  level: LogLevel
  message: string
  status?: string
  duration?: number
}

interface FilterState {
  search: string
  services: Set<string>
  levels: Set<LogLevel>
  statuses: Set<string>
}

const ANSI_RE = /\x1b\[[0-9;]*[mABCDEFGHJKLMSTfhilmnprsu]/g

function stripAnsi(s: string): string {
  return s.replace(ANSI_RE, '')
}

const SOURCES: { key: LogSource; label: string }[] = [
  { key: 'hermes', label: 'Hermes' },
  { key: 'kanban', label: 'Kanban' },
  { key: 'system', label: 'System' },
]

const LEVEL_COLORS: Record<LogLevel, { bg: string; color: string; border: string }> = {
  debug: { bg: 'rgba(90,162,240,0.1)', color: '#5aa2f0', border: 'rgba(90,162,240,0.28)' },
  info: { bg: 'rgba(45,212,191,0.1)', color: '#2dd4bf', border: 'rgba(45,212,191,0.28)' },
  warn: { bg: 'rgba(250,180,42,0.1)', color: '#f6b73c', border: 'rgba(246,183,60,0.28)' },
  error: { bg: 'rgba(251,111,111,0.1)', color: '#fb6f6f', border: 'rgba(251,111,111,0.28)' },
}

const STATUS_COLORS: Record<string, string> = {
  running: '#2dd4bf',
  idle: '#5aa2f0',
  error: '#fb6f6f',
  success: '#2dd4bf',
}

export default function Logs({ accent = ACCENT }: LogsProps) {
  const [source, setSource] = useState<LogSource>('hermes')
  const [lines, setLines] = useState<string[]>([])
  const [live, setLive] = useState(false)
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [filters, setFilters] = useState<FilterState>({
    search: '',
    services: new Set(),
    levels: new Set(),
    statuses: new Set(),
  })
  const [showFilters, setShowFilters] = useState(true)
  const [availableServices, setAvailableServices] = useState<Set<string>>(new Set())
  const [availableLevels, setAvailableLevels] = useState<Set<LogLevel>>(new Set())
  const [availableStatuses, setAvailableStatuses] = useState<Set<string>>(new Set())
  const esRef = useRef<EventSource | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)

  // Parse log entries from lines
  const parseLogEntries = (logLines: string[]): LogEntry[] => {
    return logLines
      .map((line, idx) => {
        // Simple parsing - extract basic fields from log format
        const match = line.match(/\[(.*?)\]\s+\[(.*?)\]\s+(.*?)\s*:\s*(.*)/)
        if (!match) return null

        const [, timestamp, level, service, message] = match
        return {
          id: `${idx}`,
          timestamp: timestamp || new Date().toISOString(),
          service: service || 'unknown',
          level: (level?.toLowerCase() as LogLevel) || 'info',
          message: message || line,
          status: extractStatus(message),
          duration: extractDuration(message),
        }
      })
      .filter((e) => e !== null) as LogEntry[]
  }

  const extractStatus = (msg: string): string | undefined => {
    if (msg.includes('error')) return 'error'
    if (msg.includes('success') || msg.includes('completed')) return 'success'
    if (msg.includes('running')) return 'running'
    if (msg.includes('idle')) return 'idle'
    return undefined
  }

  const extractDuration = (msg: string): number | undefined => {
    const match = msg.match(/(\d+(?:\.\d+)?)\s*(?:ms|s)/)
    if (!match) return undefined
    const num = parseFloat(match[1])
    return match[0].includes('s') && !match[0].includes('ms') ? num * 1000 : num
  }

  // Parse entries and update available filters
  useEffect(() => {
    const entries = parseLogEntries(lines)
    const services = new Set(entries.map((e) => e.service))
    const levels = new Set(entries.map((e) => e.level))
    const statuses = new Set(entries.map((e) => e.status).filter(Boolean) as string[])
    setAvailableServices(services)
    setAvailableLevels(levels)
    setAvailableStatuses(statuses)
  }, [lines])

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
      })
      .catch(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source])

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

  function toggleService(service: string) {
    const newServices = new Set(filters.services)
    if (newServices.has(service)) {
      newServices.delete(service)
    } else {
      newServices.add(service)
    }
    setFilters({ ...filters, services: newServices })
  }

  function toggleLevel(level: LogLevel) {
    const newLevels = new Set(filters.levels)
    if (newLevels.has(level)) {
      newLevels.delete(level)
    } else {
      newLevels.add(level)
    }
    setFilters({ ...filters, levels: newLevels })
  }

  function toggleStatus(status: string) {
    const newStatuses = new Set(filters.statuses)
    if (newStatuses.has(status)) {
      newStatuses.delete(status)
    } else {
      newStatuses.add(status)
    }
    setFilters({ ...filters, statuses: newStatuses })
  }

  function clearFilters() {
    setFilters({
      search: '',
      services: new Set(),
      levels: new Set(),
      statuses: new Set(),
    })
  }

  const entries = parseLogEntries(lines)

  // Apply filters
  const filteredEntries = entries.filter((entry) => {
    if (
      filters.services.size > 0 &&
      !filters.services.has(entry.service)
    ) {
      return false
    }
    if (filters.levels.size > 0 && !filters.levels.has(entry.level)) {
      return false
    }
    if (
      filters.statuses.size > 0 &&
      (!entry.status || !filters.statuses.has(entry.status))
    ) {
      return false
    }
    if (
      filters.search &&
      !entry.message.toLowerCase().includes(filters.search.toLowerCase()) &&
      !entry.service.toLowerCase().includes(filters.search.toLowerCase())
    ) {
      return false
    }
    return true
  })

  const hasActiveFilters =
    filters.search ||
    filters.services.size > 0 ||
    filters.levels.size > 0 ||
    filters.statuses.size > 0

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      {/* Header */}
      <div style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div className="flex items-center justify-between">
          <div>
            <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: '#f4f6fb' }}>Logs</div>
            <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>
              {loading ? 'Loading…' : `${filteredEntries.length} of ${lines.length} events`}
              {live && <span style={{ marginLeft: 8, color: accent }}>● live</span>}
            </div>
          </div>
          <div className="flex items-center" style={{ gap: 8 }}>
            {/* Filter button with badge */}
            <button
              onClick={() => setShowFilters(!showFilters)}
              style={{
                fontSize: 12,
                fontFamily: 'inherit',
                cursor: 'pointer',
                padding: '7px 12px',
                borderRadius: 8,
                background: showFilters ? `color-mix(in oklab, ${accent} 14%, transparent)` : 'transparent',
                border: `1px solid ${showFilters ? `color-mix(in oklab, ${accent} 40%, transparent)` : 'rgba(255,255,255,0.1)'}`,
                color: showFilters ? accent : '#9298ab',
                transition: 'all 0.15s',
                position: 'relative',
              }}
            >
              ⚙️
              {hasActiveFilters && (
                <span
                  style={{
                    position: 'absolute',
                    top: -6,
                    right: -6,
                    background: '#fb6f6f',
                    color: '#fff',
                    borderRadius: 12,
                    width: 20,
                    height: 20,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 10,
                    fontWeight: 600,
                    border: '2px solid #0a0e16',
                  }}
                >
                  {filters.services.size + filters.levels.size + filters.statuses.size}
                </span>
              )}
            </button>
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

        {/* Search bar with glass effect */}
        <div style={{ position: 'relative', width: '100%' }}>
          <svg
            style={{
              position: 'absolute',
              left: 12,
              top: '50%',
              transform: 'translateY(-50%)',
              width: 15,
              height: 15,
              color: '#666c82',
            }}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          <input
            type="text"
            placeholder="Search logs by message or service…"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            style={{
              width: '100%',
              padding: '10px 12px 10px 40px',
              fontSize: 13,
              fontFamily: 'inherit',
              background: 'rgba(17,21,31,0.55)',
              backdropFilter: 'blur(14px)',
              border: `1px solid ${filters.search ? accent : 'rgba(255,255,255,0.08)'}`,
              borderRadius: 10,
              color: '#e4e6ee',
              transition: 'all 0.15s',
              outline: 'none',
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = accent
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = filters.search ? accent : 'rgba(255,255,255,0.08)'
            }}
          />
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

      {/* Body - split into filter sidebar and log entries */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {/* Filter sidebar */}
        {showFilters && (
          <div
            style={{
              flex: 'none',
              width: 230,
              borderRight: '1px solid rgba(255,255,255,0.06)',
              overflowY: 'auto',
              padding: '16px 0',
              display: 'flex',
              flexDirection: 'column',
              gap: 0,
            }}
          >
            {/* Clear filters button */}
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                style={{
                  padding: '8px 16px',
                  fontSize: 11,
                  fontWeight: 600,
                  color: '#fb6f6f',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  textAlign: 'left',
                  marginBottom: 8,
                }}
              >
                Clear all filters
              </button>
            )}

            {/* Services filter group */}
            {availableServices.size > 0 && (
              <div style={{ padding: '0 16px', marginBottom: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#6a7088', textTransform: 'uppercase', marginBottom: 8 }}>Services</div>
                {Array.from(availableServices).map((service) => (
                  <label
                    key={service}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 8px',
                      fontSize: 12,
                      color: filters.services.has(service) ? '#e4e6ee' : '#9298ab',
                      cursor: 'pointer',
                      marginBottom: 4,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={filters.services.has(service)}
                      onChange={() => toggleService(service)}
                      style={{ cursor: 'pointer' }}
                    />
                    {service}
                  </label>
                ))}
              </div>
            )}

            {/* Levels filter group */}
            {availableLevels.size > 0 && (
              <div style={{ padding: '0 16px', marginBottom: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#6a7088', textTransform: 'uppercase', marginBottom: 8 }}>Levels</div>
                {Array.from(availableLevels).map((level) => (
                  <label
                    key={level}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 8px',
                      fontSize: 12,
                      color: filters.levels.has(level) ? '#e4e6ee' : '#9298ab',
                      cursor: 'pointer',
                      marginBottom: 4,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={filters.levels.has(level)}
                      onChange={() => toggleLevel(level)}
                      style={{ cursor: 'pointer' }}
                    />
                    <span
                      style={{
                        display: 'inline-block',
                        width: 8,
                        height: 8,
                        borderRadius: 2,
                        background: LEVEL_COLORS[level]?.color || '#999',
                      }}
                    />
                    {level.charAt(0).toUpperCase() + level.slice(1)}
                  </label>
                ))}
              </div>
            )}

            {/* Statuses filter group */}
            {availableStatuses.size > 0 && (
              <div style={{ padding: '0 16px', marginBottom: 16 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: '#6a7088', textTransform: 'uppercase', marginBottom: 8 }}>Statuses</div>
                {Array.from(availableStatuses).map((status) => (
                  <label
                    key={status}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '6px 8px',
                      fontSize: 12,
                      color: filters.statuses.has(status) ? '#e4e6ee' : '#9298ab',
                      cursor: 'pointer',
                      marginBottom: 4,
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={filters.statuses.has(status)}
                      onChange={() => toggleStatus(status)}
                      style={{ cursor: 'pointer' }}
                    />
                    <span
                      style={{
                        display: 'inline-block',
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: STATUS_COLORS[status] || '#999',
                      }}
                    />
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </label>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Log entries container */}
        <div
          ref={containerRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            overflowX: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {filteredEntries.length === 0 && !loading ? (
            <div
              style={{
                flex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#565d72',
                fontSize: 13,
              }}
            >
              No logs match your filters.
            </div>
          ) : (
            filteredEntries.map((entry) => (
              <div key={entry.id}>
                {/* Log row */}
                <div
                  onClick={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '24px 80px 1fr 60px 70px 60px 48px',
                    alignItems: 'center',
                    gap: 12,
                    padding: '8px 16px',
                    borderBottom: '1px solid rgba(255,255,255,0.02)',
                    cursor: 'pointer',
                    background: expandedId === entry.id ? 'rgba(255,255,255,0.015)' : 'transparent',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(255,255,255,0.025)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = expandedId === entry.id ? 'rgba(255,255,255,0.015)' : 'transparent'
                  }}
                >
                  {/* Expand chevron */}
                  <span
                    style={{
                      transform: expandedId === entry.id ? 'rotate(90deg)' : 'rotate(0deg)',
                      transition: 'transform 0.15s',
                      fontSize: 14,
                      color: '#6a7088',
                    }}
                  >
                    ›
                  </span>

                  {/* Time */}
                  <span style={{ fontFamily: 'monospace', fontSize: 11, color: '#818799' }}>
                    {new Date(entry.timestamp).toLocaleTimeString()}
                  </span>

                  {/* Level badge */}
                  <span
                    style={{
                      display: 'inline-block',
                      padding: '3px 8px',
                      borderRadius: 4,
                      fontSize: 10,
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      background: LEVEL_COLORS[entry.level]?.bg || 'rgba(255,255,255,0.05)',
                      color: LEVEL_COLORS[entry.level]?.color || '#9298ab',
                      border: `1px solid ${LEVEL_COLORS[entry.level]?.border || 'rgba(255,255,255,0.1)'}`,
                      width: 'fit-content',
                    }}
                  >
                    {entry.level}
                  </span>

                  {/* Service name */}
                  <span
                    style={{
                      fontSize: 12,
                      color: '#e4e6ee',
                      fontWeight: 500,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {entry.service}
                  </span>

                  {/* Message with ellipsis */}
                  <span
                    style={{
                      fontSize: 12,
                      color: '#d4d8e4',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      gridColumn: 'span 2',
                    }}
                  >
                    {entry.message}
                  </span>

                  {/* Status */}
                  {entry.status && (
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: STATUS_COLORS[entry.status] || '#9298ab',
                        textTransform: 'capitalize',
                      }}
                    >
                      {entry.status}
                    </span>
                  )}

                  {/* Duration (right-aligned) */}
                  {entry.duration && (
                    <span
                      style={{
                        fontFamily: 'monospace',
                        fontSize: 11,
                        color: '#9aa0b4',
                        textAlign: 'right',
                      }}
                    >
                      {entry.duration.toFixed(0)}ms
                    </span>
                  )}
                </div>

                {/* Expanded detail section */}
                {expandedId === entry.id && (
                  <div
                    style={{
                      padding: '12px 16px',
                      background: 'rgba(255,255,255,0.015)',
                      borderBottom: '1px solid rgba(255,255,255,0.02)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 12,
                    }}
                  >
                    {/* Message code block */}
                    <div
                      style={{
                        background: 'rgba(8,11,17,0.5)',
                        border: '1px solid rgba(255,255,255,0.06)',
                        borderRadius: 8,
                        padding: 12,
                        fontFamily: 'monospace',
                        fontSize: 11,
                        color: '#c8cfe0',
                        wordBreak: 'break-all',
                        whiteSpace: 'pre-wrap',
                        maxHeight: 150,
                        overflowY: 'auto',
                      }}
                    >
                      {entry.message}
                    </div>

                    {/* Metadata grid */}
                    <div
                      style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                        gap: 16,
                        fontSize: 12,
                      }}
                    >
                      {entry.timestamp && (
                        <div>
                          <div style={{ color: '#6a7088', fontSize: 10, marginBottom: 4 }}>TIMESTAMP</div>
                          <div style={{ fontFamily: 'monospace', color: '#e4e6ee', fontSize: 11 }}>
                            {new Date(entry.timestamp).toISOString()}
                          </div>
                        </div>
                      )}
                      {entry.duration && (
                        <div>
                          <div style={{ color: '#6a7088', fontSize: 10, marginBottom: 4 }}>DURATION</div>
                          <div style={{ fontFamily: 'monospace', color: '#e4e6ee', fontSize: 11 }}>
                            {entry.duration.toFixed(2)}ms
                          </div>
                        </div>
                      )}
                      {entry.service && (
                        <div>
                          <div style={{ color: '#6a7088', fontSize: 10, marginBottom: 4 }}>SERVICE</div>
                          <div style={{ fontFamily: 'monospace', color: '#e4e6ee', fontSize: 11 }}>
                            {entry.service}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
