interface SparklineProps {
  line: string
  area: string
  stroke: string
  fill: string
  height?: number
}

/** Small inline SVG sparkline driven by precomputed path data (viewBox 100×30). */
export default function Sparkline({ line, area, stroke, fill, height = 30 }: SparklineProps) {
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" style={{ width: '100%', height, marginTop: 7, display: 'block' }}>
      <path d={area} fill={fill} />
      <path d={line} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}
