import { useState } from 'react'
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

export default function Shell() {
  const [activePanel, setActivePanel] = useState<PanelId>('overview')
  const [accent, setAccentRaw] = useState<string>(() => {
    try { return localStorage.getItem('hermes-accent') || ACCENT } catch { return ACCENT }
  })
  const setAccent = (c: string) => {
    setAccentRaw(c)
    try { localStorage.setItem('hermes-accent', c) } catch { /* storage unavailable */ }
  }
  const rows = useAgentRows(accent)

  return (
    <InfoProvider>
      <div style={{ '--ac': accent } as React.CSSProperties} className="flex h-screen overflow-hidden">
        <StarsBackground />
        {/* Left rail */}
        <nav
          className="relative z-30 flex flex-none flex-col"
          style={{
            width: 240,
            background: 'linear-gradient(180deg, #0d121d, #090d15)',
            borderRight: '1px solid var(--border)',
            minHeight: 0,
          }}
        >
          {/* Brand */}
          <div className="flex items-center gap-3" style={{ padding: '22px 18px 18px', borderBottom: '1px solid var(--border)' }}>
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
            <div style={{ lineHeight: 1.2, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 14, letterSpacing: '0.02em', color: '#f0f2f8' }}>HERMES</div>
              <div style={{ fontSize: 11, color: '#6a7088', marginTop: 1 }}>Task Dispatcher</div>
            </div>
            <span
              className="mono"
              style={{
                marginLeft: 'auto',
                flex: 'none',
                fontSize: 9.5,
                fontWeight: 500,
                color: accent,
                background: `color-mix(in oklab, ${accent} 12%, transparent)`,
                border: `1px solid color-mix(in oklab, ${accent} 26%, transparent)`,
                borderRadius: 6,
                padding: '2px 6px',
              }}
            >
              v2.0
            </span>
          </div>

          {/* Nav groups */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden" style={{ padding: '14px 12px' }}>
            {NAV_GROUPS.map((group, gi) => (
              <div key={group.header} style={{ marginBottom: gi === 0 ? 18 : 0 }}>
                <div style={groupHeaderStyle}>{group.header}</div>
                <div className="flex flex-col" style={{ gap: 2 }}>
                  {group.items.map((item) => (
                    <NavItem
                      key={item.panel}
                      panel={item.panel}
                      label={item.label}
                      active={activePanel === item.panel}
                      accent={accent}
                      onSelect={setActivePanel}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Live agent status list */}
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
        </nav>

        {/* Main content */}
        <main className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
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
