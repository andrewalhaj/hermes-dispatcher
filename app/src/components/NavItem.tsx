import type { PanelId } from '../data/types'
import { NavIcon } from './icons'

interface NavItemProps {
  panel: PanelId
  label: string
  active: boolean
  accent: string
  onSelect: (panel: PanelId) => void
  /** Icon-only rail mode (md tablet): hide the label, center the icon. */
  collapsed?: boolean
  /** Unread count badge rendered on the icon when > 0. */
  badge?: number
}

export default function NavItem({ panel, label, active, accent, onSelect, collapsed = false, badge = 0 }: NavItemProps) {
  return (
    <button
      onClick={() => onSelect(panel)}
      title={collapsed ? label : undefined}
      className={`group relative flex w-full items-center rounded-[10px] py-[10px] text-left ${collapsed ? 'justify-center px-0 gap-0' : 'gap-[11px] px-[11px]'}`}
      style={{
        background: active ? `color-mix(in oklab, ${accent} 12%, transparent)` : 'transparent',
        border: `1px solid ${active ? `color-mix(in oklab, ${accent} 24%, transparent)` : 'transparent'}`,
        color: active ? '#f0f2f8' : '#9298ab',
        fontFamily: 'inherit',
        fontSize: 13.5,
        fontWeight: 500,
        cursor: 'pointer',
        transition: 'background 0.15s, color 0.15s, border-color 0.15s',
      }}
      onMouseEnter={(e) => {
        if (!active) {
          e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
          e.currentTarget.style.color = '#e9ebf2'
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          e.currentTarget.style.background = 'transparent'
          e.currentTarget.style.color = '#9298ab'
        }
      }}
    >
      <span
        aria-hidden="true"
        style={{
          position: 'absolute',
          left: -1,
          top: '25%',
          bottom: '25%',
          width: 3,
          borderRadius: '0 3px 3px 0',
          background: accent,
          boxShadow: `0 0 10px ${accent}, 0 0 20px ${accent}`,
          opacity: active ? 1 : 0,
          transition: 'opacity 0.15s',
        }}
      />
      <span className="relative flex w-5 flex-none items-center justify-center">
        <NavIcon panel={panel} />
        {(badge ?? 0) > 0 && (
          <span style={{
            position: 'absolute',
            top: -5,
            right: collapsed ? -5 : -7,
            minWidth: 16, height: 16,
            borderRadius: 8,
            background: '#3b82f6',
            color: '#fff',
            fontSize: 10,
            fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '0 3px',
            lineHeight: 1,
            pointerEvents: 'none',
            zIndex: 10,
          }}>
            {badge > 99 ? '99+' : badge}
          </span>
        )}
      </span>
      {!collapsed && <span>{label}</span>}
    </button>
  )
}
