interface HoverRevealProps {
  items?: string[]
  className?: string
}

const defaultItems = ['H', 'E', 'R', 'M', 'E', 'S']

export function HoverReveal({ items = defaultItems, className = '' }: HoverRevealProps) {
  if (!items.length) return null
  return (
    <ul className={`flex flex-nowrap items-center justify-center select-none list-none p-0 m-0 ${className}`}>
      {items.map((item, i) => (
        <li key={i} className="flex items-center justify-center flex-shrink-0 px-1">
          <span className="text-transparent bg-gradient-to-b from-white/90 to-white/40 bg-clip-text whitespace-nowrap">
            {item}
          </span>
        </li>
      ))}
    </ul>
  )
}
