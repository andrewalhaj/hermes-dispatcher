import type { CSSProperties, ReactNode, MouseEvent } from 'react'

interface GlassTileProps {
  children: ReactNode
  style?: CSSProperties
  className?: string
  padding?: string
  cornerRadius?: number
  onClick?: () => void
  onMouseEnter?: (e: MouseEvent<HTMLDivElement>) => void
  onMouseLeave?: (e: MouseEvent<HTMLDivElement>) => void
}

export default function GlassTile({
  children,
  style,
  className,
  padding = '18px',
  cornerRadius = 14,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: GlassTileProps) {
  return (
    <div
      className={className}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{
        position: 'relative',
        borderRadius: cornerRadius,
        border: '1px solid rgba(255,255,255,0.07)',
        background: 'rgba(14, 19, 30, 0.82)',
        backdropFilter: 'blur(18px) saturate(130%)',
        WebkitBackdropFilter: 'blur(18px) saturate(130%)',
        boxShadow: '0 0 0 1px rgba(255,255,255,0.03) inset, 0 8px 32px rgba(0,0,0,0.4)',
        padding,
        ...style,
      }}
    >
      {children}
    </div>
  )
}
