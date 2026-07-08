import { useEffect, useState } from 'react'
import Markdown from './Markdown'

/** Shape returned by GET /api/kanban/linear-issue. */
interface LinearLabel {
  name: string
  color: string
}
interface LinearComment {
  body: string
  createdAt: string
  author: string
}
interface LinearIssue {
  identifier: string
  title: string
  description: string
  url: string
  priority: number | null
  priorityLabel: string
  state: { name: string; color: string }
  labels: LinearLabel[]
  comments: LinearComment[]
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; issue: LinearIssue }

function fmtDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Renders the full Linear issue inline inside the card detail drawer:
 * description (markdown), labels, priority, state, and the comment thread.
 * Data is fetched lazily when the section mounts (i.e. when a card is opened).
 */
export default function LinearIssueSection({ url, accent }: { url: string; accent: string }) {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    let cancelled = false
    setState({ kind: 'loading' })
    fetch(`/api/kanban/linear-issue?url=${encodeURIComponent(url)}`)
      .then(async (r) => {
        if (!r.ok) {
          let detail = `HTTP ${r.status}`
          try {
            const body = await r.json()
            if (body?.detail) detail = String(body.detail)
          } catch {
            /* non-JSON error body */
          }
          throw new Error(detail)
        }
        return r.json() as Promise<LinearIssue>
      })
      .then((issue) => {
        if (!cancelled) setState({ kind: 'ready', issue })
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setState({ kind: 'error', message: err instanceof Error ? err.message : 'Failed to load' })
      })
    return () => {
      cancelled = true
    }
  }, [url])

  return (
    <div
      style={{
        marginTop: 22,
        border: '1px solid var(--tile-border)',
        borderRadius: 12,
        overflow: 'hidden',
        background: 'rgba(255,255,255,0.02)',
      }}
    >
      {/* Section header */}
      <div
        className="flex items-center justify-between"
        style={{
          gap: 10,
          padding: '11px 14px',
          background: 'linear-gradient(180deg, rgba(94,106,210,0.16), transparent)',
          borderBottom: '1px solid rgba(255,255,255,0.05)',
        }}
      >
        <span className="flex items-center" style={{ gap: 8 }}>
          {/* Linear glyph */}
          <svg width="14" height="14" viewBox="0 0 100 100" aria-hidden="true">
            <path
              fill="#5e6ad2"
              d="M1.2 61.3a1 1 0 0 1 1.7-.5l36.3 36.3a1 1 0 0 1-.5 1.7A50 50 0 0 1 1.2 61.3ZM.1 47.4a1 1 0 0 0 .3.8L51.8 99.6a1 1 0 0 0 .8.3 50.3 50.3 0 0 0 8.6-1.4 1 1 0 0 0 .5-1.7L3.2 38.3a1 1 0 0 0-1.7.5A50.3 50.3 0 0 0 .1 47.4ZM6 27.2a1 1 0 0 0 .2 1.1l65.5 65.5a1 1 0 0 0 1.1.2 50.4 50.4 0 0 0 6.3-3.6 1 1 0 0 0 .1-1.5L11 20.8a1 1 0 0 0-1.5.1A50.4 50.4 0 0 0 6 27.2ZM18.7 11.2a1 1 0 0 1-.1-1.4A50 50 0 0 1 89.8 80.9a1 1 0 0 1-1.4.1L18.7 11.2Z"
            />
          </svg>
          <span style={{ fontSize: 12.5, fontWeight: 600, color: '#dde0ea', letterSpacing: '0.01em' }}>
            Linear Issue
          </span>
          {state.kind === 'ready' && (
            <span
              className="mono"
              style={{ fontSize: 10.5, color: '#8c92a6', background: 'rgba(255,255,255,0.06)', borderRadius: 6, padding: '1px 6px' }}
            >
              {state.issue.identifier}
            </span>
          )}
        </span>
        <a
          href={state.kind === 'ready' ? state.issue.url : url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center"
          style={{ gap: 5, fontSize: 11, color: accent, textDecoration: 'none', whiteSpace: 'nowrap' }}
        >
          Open in Linear
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M7 17 17 7M9 7h8v8" />
          </svg>
        </a>
      </div>

      {/* Body */}
      <div style={{ padding: '14px' }}>
        {state.kind === 'loading' && (
          <div style={{ fontSize: 12.5, color: '#818799', padding: '8px 0' }}>Loading Linear issue…</div>
        )}

        {state.kind === 'error' && (
          <div style={{ fontSize: 12.5, color: '#fb8c8c', padding: '8px 0' }}>
            Couldn't load Linear issue: {state.message}
          </div>
        )}

        {state.kind === 'ready' && (
          <>
            {/* Meta: state, priority, labels */}
            <div className="flex flex-wrap items-center" style={{ gap: 7, marginBottom: 12 }}>
              {state.issue.state.name && (
                <span
                  className="inline-flex items-center"
                  style={{
                    gap: 6,
                    fontSize: 11,
                    color: '#cfd3e0',
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 6,
                    padding: '2px 8px',
                  }}
                >
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: state.issue.state.color || '#8c92a6' }} />
                  {state.issue.state.name}
                </span>
              )}
              {state.issue.priorityLabel && (
                <span
                  style={{ fontSize: 11, color: '#cfd3e0', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 6, padding: '2px 8px' }}
                >
                  {state.issue.priorityLabel}
                </span>
              )}
              {state.issue.labels.map((l) => (
                <span
                  key={l.name}
                  className="inline-flex items-center"
                  style={{ gap: 5, fontSize: 11, color: '#cfd3e0', background: `${l.color || '#8c92a6'}1f`, border: `1px solid ${l.color || '#8c92a6'}55`, borderRadius: 6, padding: '2px 8px' }}
                >
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: l.color || '#8c92a6' }} />
                  {l.name}
                </span>
              ))}
            </div>

            {/* Description */}
            {state.issue.description ? (
              <Markdown
                text={state.issue.description}
                style={{ fontSize: 13, color: 'var(--text-body)', ['--accent' as string]: accent } as React.CSSProperties}
              />
            ) : (
              <div style={{ fontSize: 12.5, color: '#818799', fontStyle: 'italic' }}>No description.</div>
            )}

            {/* Comments */}
            {state.issue.comments.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <div
                  style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.07em', color: '#818799', marginBottom: 10 }}
                >
                  {state.issue.comments.length} Comment{state.issue.comments.length === 1 ? '' : 's'}
                </div>
                <div className="flex flex-col" style={{ gap: 11 }}>
                  {state.issue.comments.map((c, i) => (
                    <div
                      key={i}
                      style={{
                        borderLeft: '2px solid rgba(94,106,210,0.5)',
                        paddingLeft: 11,
                      }}
                    >
                      <div className="flex items-center" style={{ gap: 8, marginBottom: 3 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: '#dde0ea' }}>{c.author}</span>
                        <span className="mono" style={{ fontSize: 10.5, color: '#6a7088' }}>{fmtDate(c.createdAt)}</span>
                      </div>
                      <Markdown
                        text={c.body}
                        style={{ fontSize: 12.5, color: 'var(--text-body)', ['--accent' as string]: accent } as React.CSSProperties}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
