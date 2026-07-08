import { useLinearIssues } from './useLinearIssues'
import { useInfo } from '../TileInfoDrawer'

const cardLabelStyle: React.CSSProperties = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
  color: 'var(--text-faint)',
}

const ACCENT = '#5e6ad2' // Linear brand purple-blue

/** Linear logo glyph (the four-bar mark), inline SVG, zero deps. */
const LinearMark = ({ color }: { color: string }) => (
  <svg width="15" height="15" viewBox="0 0 100 100" fill={color} aria-hidden>
    <path d="M1.2 61.4a1 1 0 0 0 .3.9l36.2 36.2a1 1 0 0 0 .9.3C18.6 96.2 3.8 81.4 1.2 61.4Z" />
    <path d="M.1 46.9a1 1 0 0 0 .3.8l52 52a1 1 0 0 0 .8.3 50 50 0 0 0 9.2-1.5L1.6 37.7A50 50 0 0 0 .1 46.9Z" />
    <path d="M4.3 31.3a1 1 0 0 0 .2 1.1l63.2 63.2a1 1 0 0 0 1.1.2 50.3 50.3 0 0 0 6.5-3L7.3 24.8a50.3 50.3 0 0 0-3 6.5Z" />
    <path d="M12.4 19.5a1 1 0 0 0-.1 1.3l67 67a1 1 0 0 0 1.3-.1A50 50 0 1 0 12.4 19.5Z" />
  </svg>
)

/**
 * Open Issues tile — live Linear issue counts for the Overview dashboard.
 * Renders "<open> open · <urgent> urgent · <stale> stale" from real data,
 * polled every 5 minutes via useLinearIssues. Click opens the info drawer.
 */
export default function OpenIssuesTile() {
  const { data, loading } = useLinearIssues()
  const { openInfo } = useInfo()
  const unreachable = !!data.error && data.updated_at === 0

  const segs: { value: number; label: string; color: string }[] = [
    { value: data.open, label: 'open', color: '#e4e6ee' },
    { value: data.urgent, label: 'urgent', color: '#fb6f6f' },
    { value: data.stale, label: 'stale', color: '#fbbf24' },
  ]

  return (
    <div
      onClick={() =>
        openInfo({
          category: 'Overview · Linear',
          title: 'Open Issues',
          accent: ACCENT,
          desc: 'Live issue counts from the Hermesjarvis Linear team. Open = backlog/unstarted/started/triage. Urgent = priority Urgent/No-priority (0–1). Stale = untouched for 7+ days. Refreshed every 5 minutes.',
          stats: [
            { label: 'Open', value: String(data.open) },
            { label: 'Urgent', value: String(data.urgent) },
            { label: 'Stale (7d+)', value: String(data.stale) },
            ...(data.error ? [{ label: 'Status', value: data.error }] : []),
          ],
        })
      }
      className="relative overflow-hidden"
      style={{
        background: 'var(--s3)',
        border: '1px solid var(--tile-border)',
        borderRadius: 14,
        padding: 18,
        cursor: 'pointer',
        animation: 'hcellin 0.45s ease backwards',
        animationDelay: '0.28s',
      }}
    >
      <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
        <div className="inline-flex items-center" style={{ gap: 8 }}>
          <LinearMark color={ACCENT} />
          <span style={cardLabelStyle}>Open Issues</span>
        </div>
        <span
          style={{
            fontSize: 10.5,
            color: unreachable ? '#fbbf24' : ACCENT,
            background: unreachable ? 'rgba(251,191,36,0.1)' : 'rgba(94,106,210,0.12)',
            border: `1px solid ${unreachable ? 'rgba(251,191,36,0.28)' : 'rgba(94,106,210,0.3)'}`,
            borderRadius: 6,
            padding: '2px 8px',
          }}
        >
          {unreachable ? 'unreachable' : 'Linear · live'}
        </span>
      </div>

      {unreachable ? (
        <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-faint)', fontSize: 12 }}>
          Linear data unavailable
        </div>
      ) : (
        <div className="flex items-center" style={{ gap: 14, flexWrap: 'wrap' }}>
          {segs.map((s, i) => (
            <div key={s.label} className="flex items-center" style={{ gap: 14 }}>
              {i > 0 && (
                <span style={{ color: 'var(--text-faint)', fontSize: 18, lineHeight: 1 }}>·</span>
              )}
              <div className="flex items-baseline" style={{ gap: 6 }}>
                <span
                  style={{
                    fontFamily: 'var(--font-display)',
                    fontWeight: 700,
                    fontSize: 30,
                    lineHeight: 1,
                    color: s.color,
                    opacity: loading ? 0.4 : 1,
                    transition: 'opacity 0.3s',
                  }}
                >
                  {loading ? '—' : s.value}
                </span>
                <span
                  style={{
                    fontSize: 11.5,
                    textTransform: 'uppercase',
                    letterSpacing: '0.07em',
                    color: 'var(--text-muted)',
                  }}
                >
                  {s.label}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
