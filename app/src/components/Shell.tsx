import { useState, useEffect } from 'react'
import type { PanelId } from '../data/types'
import { ACCENT } from '../data/agents'
import { useAgentRows } from '../data/fleet'
import { BrandIcon } from './icons'
import NavItem from './NavItem'
import { InfoProvider } from './TileInfoDrawer'
import TileInfoDrawer from './TileInfoDrawer'
import Overview from './panels/Overview'
import Chat from './panels/Chat'
import KanbanPanel from './panels/KanbanPanel'
import Agents from './panels/Agents'
import Skills from './panels/Skills'
import Insights from './panels/Insights'
import Sessions from './panels/Sessions'
import Memory from './panels/Memory'
import Logs from './panels/Logs'
import Settings from './panels/Settings'
import Placeholder from './panels/Placeholder'
import StarsBackground from './StarsBackground'

interface NavGroup {
  header: string
  items: { panel: PanelId; label: string }[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    header: 'Workspace',
    items: [
      { panel: 'overview', label: 'Overview' },
      { panel: 'chat', label: 'Chat' },
      { panel: 'kanban', label: 'Kanban' },
      { panel: 'agents', label: 'Agents' },
    ],
  },
  {
    header: 'System',
    items: [
      { panel: 'plugins', label: 'Skills' },
      { panel: 'memory', label: 'Memory' },
      { panel: 'logs', label: 'Logs' },
      { panel: 'insights', label: 'Insights' },
      { panel: 'sessions', label: 'Sessions' },
      { panel: 'settings', label: 'Settings' },
    ],
  },
]

const PANEL_LABELS: Record<PanelId, string> = {
  overview: 'Overview',
  chat: 'Chat',
  kanban: 'Kanban',
  agents: 'Agents',
  plugins: 'Skills',
  memory: 'Memory',
  logs: 'Logs',
  insights: 'Insights',
  sessions: 'Sessions',
  settings: 'Settings',
}

const groupHeaderStyle: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
  color: '#565d72',
  padding: '0 9px',
  marginBottom: 8,
}

/** Render the active panel. Kept outside the rail so InfoProvider context wraps
 *  every panel uniformly. */
function PanelView({ panel, accent, setAccent, setPanel }: { panel: PanelId; accent: string; setAccent: (c: string) => void; setPanel: (p: PanelId) => void }) {
  switch (panel) {
    case 'overview':
      return <Overview accent={accent} navigateTo={setPanel} />
    case 'chat':
      return <Chat accent={accent} />
    case 'kanban':
      return <KanbanPanel accent={accent} />
    case 'agents':
      return <Agents accent={accent} />
    case 'plugins':
      return <Skills accent={accent} />
    case 'insights':
      return <Insights accent={accent} />
    case 'sessions':
      return <Sessions accent={accent} />
    case 'memory':
      return <Memory accent={accent} />
    case 'logs':
      return <Logs accent={accent} />
    case 'settings':
      return <Settings accent={accent} onAccentChange={setAccent} />
    default:
      return <Placeholder name={PANEL_LABELS[panel]} />
  }
}

/** Responsive breakpoint state derived from window width.
 *  xl ≥1280 | lg 1024–1279 | md 768–1023 | <768 mobile. */
type Bp = 'xl' | 'lg' | 'md' | 'mobile'
function bpFor(w: number): Bp {
  if (w >= 1280) return 'xl'
  if (w >= 1024) return 'lg'
  if (w >= 768) return 'md'
  return 'mobile'
}

/** Hamburger / close icon for the mobile drawer toggle. */
function MenuIcon({ open }: { open: boolean }) {
  return (
    <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      {open ? (
        <>
          <line x1={18} y1={6} x2={6} y2={18} />
          <line x1={6} y1={6} x2={18} y2={18} />
        </>
      ) : (
        <>
          <line x1={3} y1={6} x2={21} y2={6} />
          <line x1={3} y1={12} x2={21} y2={12} />
          <line x1={3} y1={18} x2={21} y2={18} />
        </>
      )}
    </svg>
  )
}

export default function Shell() {
  const [activePanel, setActivePanel] = useState<PanelId>('overview')
  const [bp, setBp] = useState<Bp>(() => bpFor(typeof window !== 'undefined' ? window.innerWidth : 1280))
  // Sidebar drawer open state — only meaningful at the mobile breakpoint.
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => (typeof window !== 'undefined' ? window.innerWidth >= 768 : true))
  const [accent, setAccentRaw] = useState<string>(() => {
    try { return localStorage.getItem('hermes-accent') || ACCENT } catch { return ACCENT }
  })
  const setAccent = (c: string) => {
    setAccentRaw(c)
    try { localStorage.setItem('hermes-accent', c) } catch { /* storage unavailable */ }
  }
  const rows = useAgentRows(accent)

  // Track viewport breakpoint; auto-collapse the drawer below md (768px) and
  // auto-open it again when returning to a width that shows the rail inline.
  useEffect(() => {
    function onResize() {
      const next = bpFor(window.innerWidth)
      setBp((prev) => {
        if (prev !== next) {
          if (next === 'mobile') setSidebarOpen(false)
          else setSidebarOpen(true)
        }
        return next
      })
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const isMobile = bp === 'mobile'
  const isRail = bp === 'md' // icon-only rail
  const railWidth = isRail ? 52 : bp === 'lg' ? 200 : 240

  function selectPanel(p: PanelId) {
    setActivePanel(p)
    if (isMobile) setSidebarOpen(false)
  }

  return (
    <InfoProvider>
      <div style={{ '--ac': accent } as React.CSSProperties} className="flex h-screen overflow-hidden">
        <StarsBackground />
        {/* Mobile backdrop scrim — closes the drawer on tap */}
        {isMobile && sidebarOpen && (
          <div
            onClick={() => setSidebarOpen(false)}
            className="absolute inset-0 z-40"
            style={{ background: 'rgba(0,0,0,0.55)', animation: 'hscrimin 0.2s ease' }}
          />
        )}
        {/* Left rail */}
        <nav
          className={`flex flex-col ${isMobile ? 'absolute left-0 top-0 z-50 h-full' : 'relative z-30 flex-none'}`}
          style={{
            width: railWidth,
            transform: isMobile && !sidebarOpen ? 'translateX(-100%)' : 'translateX(0)',
            transition: 'transform 0.24s var(--ease-out)',
            background: 'linear-gradient(180deg, #0d121d, #090d15)',
            borderRight: '1px solid var(--border)',
            minHeight: 0,
            boxShadow: isMobile && sidebarOpen ? '0 0 40px rgba(0,0,0,0.6)' : 'none',
          }}
        >
          {/* Brand */}
          <div className="flex items-center gap-3" style={{ padding: isRail ? '22px 0 18px' : '22px 18px 18px', justifyContent: isRail ? 'center' : 'flex-start', borderBottom: '1px solid var(--border)' }}>
            <span
              className="inline-flex flex-none items-center justify-center"
              style={{
                width: 38,
                height: 38,
                borderRadius: 11,
                background: `linear-gradient(135deg, ${accent}, #c2410c)`,
                boxShadow: `0 0 22px color-mix(in oklab, ${accent} 50%, transparent), 0 4px 16px rgba(0,0,0,0.5)`,
              }}
            >
              <BrandIcon />
            </span>
            {!isRail && (
            <div style={{ lineHeight: 1.2, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, letterSpacing: '0.02em', color: '#f0f2f8' }}>HERMES</div>
              <div style={{ fontSize: 11, color: '#6a7088', marginTop: 1 }}>Task Dispatcher</div>
            </div>
            )}
          </div>

          {/* Nav groups */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden" style={{ padding: isRail ? '14px 8px' : '14px 12px' }}>
            {NAV_GROUPS.map((group, gi) => (
              <div key={group.header} style={{ marginBottom: gi === 0 ? 18 : 0 }}>
                {!isRail && <div style={groupHeaderStyle}>{group.header}</div>}
                <div className="flex flex-col" style={{ gap: 2 }}>
                  {group.items.map((item) => (
                    <NavItem
                      key={item.panel}
                      panel={item.panel}
                      label={item.label}
                      active={activePanel === item.panel}
                      accent={accent}
                      collapsed={isRail}
                      onSelect={selectPanel}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Live agent status list — hidden in icon-only rail mode */}
          {!isRail && (
          <div style={{ marginTop: 'auto', padding: '14px 12px 18px', borderTop: '1px solid var(--border)' }}>
            <div style={{ ...groupHeaderStyle, padding: '0 5px', marginBottom: 10 }}>Agents</div>
            <div className="flex flex-col" style={{ gap: 5 }}>
              {rows.map((ag) => (
                <button
                  key={ag.key}
                  onClick={() => setActivePanel('chat')}
                  className="flex w-full items-center justify-between"
                  style={{
                    gap: 9,
                    padding: '8px 11px',
                    borderRadius: 10,
                    background: 'rgba(255,255,255,0.028)',
                    border: '1px solid rgba(255,255,255,0.07)',
                    cursor: 'pointer',
                    transition: 'border-color 0.15s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)')}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.07)')}
                >
                  <span className="flex min-w-0 items-center" style={{ gap: 9 }}>
                    <span className="flex-none" style={{ width: 7, height: 7, borderRadius: '50%', background: ag.dot, boxShadow: ag.dotGlow }} />
                    <span className="mono overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: 11.5, fontWeight: 500, color: '#c6cad8' }}>
                      {ag.name}
                    </span>
                  </span>
                  <span
                    className="flex-none"
                    style={{
                      fontSize: 9,
                      fontWeight: 700,
                      letterSpacing: '0.05em',
                      padding: '2px 7px',
                      borderRadius: 99,
                      color: ag.badgeColor,
                      background: ag.badgeBg,
                    }}
                  >
                    {ag.badge}
                  </span>
                </button>
              ))}
            </div>
          </div>
          )}
        </nav>

        {/* Main content */}
        <main className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
          {/* Mobile top bar: hamburger to open the drawer (only <768px) */}
          {isMobile && (
            <div
              className="flex flex-none items-center gap-3"
              style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)', background: 'rgba(8,11,17,0.6)' }}
            >
              <button
                onClick={() => setSidebarOpen((v) => !v)}
                aria-label={sidebarOpen ? 'Close menu' : 'Open menu'}
                className="inline-flex items-center justify-center"
                style={{ width: 38, height: 38, flex: 'none', borderRadius: 10, background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)', color: '#c6cad8', cursor: 'pointer' }}
              >
                <MenuIcon open={sidebarOpen} />
              </button>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, letterSpacing: '0.02em', color: '#f0f2f8' }}>
                {PANEL_LABELS[activePanel]}
              </span>
            </div>
          )}
          <div key={activePanel} style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, minWidth: 0, animation: 'hpanelin 0.38s var(--ease-out, cubic-bezier(0.16,1,0.3,1)) both' }}>
            <PanelView panel={activePanel} accent={accent} setAccent={setAccent} setPanel={setActivePanel} />
          </div>
        </main>

        {/* Universal tile info drawer (shared across panels) */}
        <TileInfoDrawer />
      </div>
    </InfoProvider>
  )
}
