import type { ReactNode } from 'react'

interface ComposerDropdownProps {
  /** Unique menu key (profile/folder/model/reasoning). */
  menuKey: string
  /** Currently selected value — also keys the label span so it re-animates on change. */
  value: string
  options: string[]
  open: boolean
  /** Trigger visual variant. 'accent' = borderless amber (Profile); 'pill' = bordered pill. */
  variant: 'accent' | 'pill'
  icon: ReactNode
  minWidth: number
  onToggle: () => void
  onPick: (value: string) => void
}

export default function ComposerDropdown({
  value,
  options,
  open,
  variant,
  icon,
  minWidth,
  onToggle,
  onPick,
}: ComposerDropdownProps) {
  const isAccent = variant === 'accent'
  return (
    <span style={{ position: 'relative', display: 'inline-flex', zIndex: 45 }}>
      <button
        onClick={(e) => {
          e.stopPropagation()
          onToggle()
        }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          background: 'none',
          border: isAccent ? 'none' : '1px solid rgba(255,255,255,0.12)',
          borderRadius: isAccent ? 8 : 20,
          padding: isAccent ? '5px 7px' : '5px 11px',
          fontSize: 12,
          fontWeight: isAccent ? 600 : 400,
          color: isAccent ? 'var(--ac)' : '#c6cad8',
          fontFamily: 'inherit',
          cursor: 'pointer',
          transition: 'background 0.15s, border-color 0.15s',
        }}
        onMouseEnter={(e) => {
          if (isAccent) e.currentTarget.style.background = 'rgba(255,255,255,0.05)'
          else e.currentTarget.style.borderColor = 'rgba(255,255,255,0.24)'
        }}
        onMouseLeave={(e) => {
          if (isAccent) e.currentTarget.style.background = 'none'
          else e.currentTarget.style.borderColor = 'rgba(255,255,255,0.12)'
        }}
      >
        {icon}
        {/* key={value} remounts the span so the hdropswap keyframe replays on change */}
        <span key={value} style={{ display: 'inline-block', animation: 'hdropswap 0.24s cubic-bezier(0.16,1,0.3,1)' }}>
          {value}
        </span>
        <svg width={11} height={11} viewBox="0 0 24 24" fill="none" stroke={isAccent ? 'currentColor' : '#9298ab'} strokeWidth={2}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
            marginBottom: 8,
            minWidth,
            background: '#0c1119',
            border: '1px solid rgba(255,255,255,0.12)',
            borderRadius: 11,
            padding: 6,
            boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
            animation: 'hmenuup 0.16s ease',
          }}
        >
          {options.map((opt) => {
            const selected = opt === value
            return (
              <div
                key={opt}
                onClick={(e) => {
                  e.stopPropagation()
                  onPick(opt)
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  padding: '8px 10px',
                  borderRadius: 8,
                  fontSize: 12.5,
                  color: selected ? '#e9ebf2' : '#c6cad8',
                  cursor: 'pointer',
                  background: selected ? 'rgba(255,255,255,0.05)' : 'transparent',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = selected ? 'rgba(255,255,255,0.05)' : 'transparent')}
              >
                <span>{opt}</span>
                {selected && (
                  <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="var(--ac)" strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                )}
              </div>
            )
          })}
        </div>
      )}
    </span>
  )
}
