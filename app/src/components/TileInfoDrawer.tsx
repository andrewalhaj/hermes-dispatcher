import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { InfoObject } from '../data/info'
import Markdown from './Markdown'
import LinearIssueSection from './LinearIssueSection'

export type { InfoObject, InfoStat } from '../data/info'

interface InfoContextValue {
  tileInfo: InfoObject | null
  openInfo: (o: InfoObject) => void
  closeInfo: () => void
}

const InfoContext = createContext<InfoContextValue | null>(null)

/**
 * Provides the universal tile-info drawer state. Any panel can call
 * `useInfo().openInfo({...})` to surface the shared right-side drawer.
 */
export function InfoProvider({ children }: { children: React.ReactNode }) {
  const [tileInfo, setTileInfo] = useState<InfoObject | null>(null)

  const openInfo = useCallback((o: InfoObject) => setTileInfo(o), [])
  const closeInfo = useCallback(() => setTileInfo(null), [])

  // Close the drawer on Escape. Registered here at the always-mounted provider
  // level so the listener is never tied to the conditionally-rendered drawer.
  // setTileInfo is stable, so a no-deps effect registers the listener exactly
  // once for the lifetime of the app. Firing setTileInfo(null) when already
  // null is a harmless no-op.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setTileInfo(null)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const value = useMemo<InfoContextValue>(
    () => ({ tileInfo, openInfo, closeInfo }),
    [tileInfo, openInfo, closeInfo],
  )

  return <InfoContext.Provider value={value}>{children}</InfoContext.Provider>
}

/** Hook into the shared tile-info drawer. */
export function useInfo(): InfoContextValue {
  const ctx = useContext(InfoContext)
  if (!ctx) throw new Error('useInfo must be used within an InfoProvider')
  return ctx
}

/**
 * The shared right-side info drawer. Rendered once at the Shell root; it reads
 * the active `InfoObject` from context and animates in over a scrim. Clicking
 * the scrim or the close button dismisses it.
 */
export default function TileInfoDrawer() {
  const { tileInfo, closeInfo } = useInfo()

  if (!tileInfo) return null

  const accent = tileInfo.accent
  const hasValue = tileInfo.value != null && tileInfo.value !== ''
  const hasStats = tileInfo.stats.length > 0
  const hasAction = !!tileInfo.actionLabel

  return (
    <>
      {/* Scrim */}
      <div
        onClick={closeInfo}
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 64,
          background: 'rgba(4,6,10,0.5)',
          backdropFilter: 'blur(2px)',
          animation: 'hscrimin 0.2s ease',
        }}
      />
      {/* Drawer */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          zIndex: 65,
          width: 408,
          maxWidth: '92vw',
          background: '#0b0f17',
          borderLeft: '1px solid var(--tile-border)',
          boxShadow: '-22px 0 60px rgba(0,0,0,0.5)',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          animation: 'hdrawerin 0.3s cubic-bezier(0.16,1,0.3,1)',
        }}
      >
        <div style={{ flex: 'none', height: 3, background: accent, boxShadow: `0 0 16px ${accent}` }} />
        <div
          className="flex items-start justify-between"
          style={{ flex: 'none', gap: 14, padding: '20px 22px 0' }}
        >
          <div style={{ minWidth: 0 }}>
            <span
              style={{
                display: 'inline-block',
                fontSize: 9.5,
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                color: '#818799',
                background: 'rgba(255,255,255,0.05)',
                borderRadius: 5,
                padding: '3px 7px',
              }}
            >
              {tileInfo.category}
            </span>
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 600,
                fontSize: 22,
                letterSpacing: '0.01em',
                color: 'var(--text-primary)',
                marginTop: 11,
                textWrap: 'pretty',
              }}
            >
              {tileInfo.title}
            </div>
          </div>
          <button
            onClick={closeInfo}
            className="inline-flex flex-none items-center justify-center"
            style={{
              width: 32,
              height: 32,
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.08)',
              borderRadius: 9,
              color: '#9aa0b4',
              cursor: 'pointer',
              transition: 'color 0.15s, background 0.15s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = '#f4f6fb'
              e.currentTarget.style.background = 'rgba(255,255,255,0.1)'
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = '#9aa0b4'
              e.currentTarget.style.background = 'rgba(255,255,255,0.05)'
            }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" aria-hidden="true">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '18px 22px 26px' }}>
          {hasValue && (
            <div
              style={{
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
                fontSize: 40,
                lineHeight: 1,
                color: accent,
                marginBottom: 16,
              }}
            >
              {tileInfo.value}
            </div>
          )}
          <Markdown
            text={tileInfo.desc}
            style={
              {
                fontSize: 13.5,
                color: 'var(--text-body)',
                textWrap: 'pretty',
                ['--accent' as string]: accent,
              } as React.CSSProperties
            }
          />
          {hasStats && (
            <div
              className="flex flex-col"
              style={{
                gap: 1,
                marginTop: 20,
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid var(--tile-border)',
                borderRadius: 11,
                overflow: 'hidden',
              }}
            >
              {tileInfo.stats.map((row, i) => (
                <div
                  key={`${row.label}-${i}`}
                  className="flex items-center justify-between"
                  style={{ gap: 14, background: 'var(--s3)', padding: '12px 14px' }}
                >
                  <span style={{ fontSize: 12, color: '#818799' }}>{row.label}</span>
                  <span className="mono" style={{ fontSize: 13, color: '#e4e6ee' }}>{row.value}</span>
                </div>
              ))}
            </div>
          )}
          {tileInfo.linearUrl && (
            <LinearIssueSection url={tileInfo.linearUrl} accent={accent} />
          )}
          {hasAction && (
            <button
              onClick={tileInfo.onAction ?? closeInfo}
              className="flex w-full items-center justify-center"
              style={{
                gap: 9,
                marginTop: 22,
                padding: 12,
                borderRadius: 11,
                background: accent,
                border: 'none',
                color: '#0c0f17',
                fontFamily: 'inherit',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'filter 0.15s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.filter = 'brightness(1.08)')}
              onMouseLeave={(e) => (e.currentTarget.style.filter = 'none')}
            >
              {tileInfo.actionLabel}
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </>
  )
}
