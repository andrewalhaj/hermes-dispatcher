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
}

export default function NavItem({ panel, label, active, accent, onSelect, collapsed = false }: NavItemProps) {
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
      <span className="flex w-5 flex-none items-center justify-center">
        <NavIcon panel={panel} />
      </span>
      {!collapsed && <span>{label}</span>}
    </button>
  )
}
