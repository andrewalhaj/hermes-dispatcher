interface PlaceholderProps {
  name: string
}

export default function Placeholder({ name }: PlaceholderProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center" style={{ minHeight: 0, padding: 40 }}>
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontWeight: 600,
          fontSize: 22,
          color: 'var(--text-primary)',
          letterSpacing: '-0.01em',
        }}
      >
        {name}
      </div>
      <p style={{ marginTop: 8, fontSize: 13, color: 'var(--text-faint)' }}>{name} — coming soon</p>
    </div>
  )
}
