import LiquidGlass from "liquid-glass-react"
import type { CSSProperties, ReactNode } from "react"

interface GlassTileProps {
  children: ReactNode
  style?: CSSProperties
  className?: string
  padding?: string
  cornerRadius?: number
  onClick?: () => void
  onMouseEnter?: (e: React.MouseEvent<HTMLElement>) => void
  onMouseLeave?: (e: React.MouseEvent<HTMLElement>) => void
}

export default function GlassTile({
  children,
  style,
  className,
  padding = "18px",
  cornerRadius = 14,
  onClick,
  onMouseEnter,
  onMouseLeave,
}: GlassTileProps) {
  return (
    <div
      className={className}
      style={{ position: "relative", ...style }}
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <LiquidGlass
        displacementScale={45}
        blurAmount={0.05}
        saturation={110}
        aberrationIntensity={1.5}
        elasticity={0.1}
        cornerRadius={cornerRadius}
        padding={padding}
        overLight={false}
        mode="standard"
        style={{
          background: "rgba(14, 19, 30, 0.97)",
          border: "1px solid rgba(255,255,255,0.06)",
          width: "100%",
          height: "100%",
        }}
      >
        {children}
      </LiquidGlass>
    </div>
  )
}
