import { planStatusMeta, planSteps } from '../../data/chat'
import type { PlanStep } from '../../data/types'

interface PlanBlockProps {
  msgId: string
  accent: string
  mainOpen: boolean
  stepOpen: Record<string, boolean>
  onToggleMain: () => void
  onToggleStep: (stepKey: string) => void
}

const Spinner = ({ size = 16, stroke }: { size?: number; stroke: string }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={stroke}
    strokeWidth={2.4}
    strokeLinecap="round"
    style={{ flex: 'none', animation: 'hspin 0.85s linear infinite' }}
  >
    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
  </svg>
)

const Check = ({ size = 16, stroke, sw = 2.6 }: { size?: number; stroke: string; sw?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none' }}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
)

const Chevron = ({ size = 14, rotated }: { size?: number; rotated: boolean }) => (
  <span style={{ color: '#565d72', display: 'inline-flex', transform: rotated ? 'rotate(-90deg)' : 'rotate(0deg)', transition: 'transform 0.22s' }}>
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 9l6 6 6-6" />
    </svg>
  </span>
)

/** Status node inside the timeline ring. */
function StepNode({ step, ringColor }: { step: PlanStep; ringColor: string }) {
  switch (step.status) {
    case 'success':
      return <Check size={13} stroke="currentColor" sw={2.6} />
    case 'active':
      return <Spinner size={13} stroke="currentColor" />
    case 'error':
      return (
        <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2 1 21h22L12 2z" />
          <path d="M12 9v5" />
          <path d="M12 18h.01" />
        </svg>
      )
    default:
      return <span style={{ width: 5, height: 5, borderRadius: '50%', background: ringColor }} />
  }
}

export default function PlanBlock({ msgId, accent, mainOpen, stepOpen, onToggleMain, onToggleStep }: PlanBlockProps) {
  const steps = planSteps(accent)
  const hasActive = steps.some((s) => s.status === 'active')
  const allSuccess = steps.every((s) => s.status === 'success')

  const planTitle = hasActive ? 'Hermes is planning the dispatch' : allSuccess ? 'Dispatch plan ready' : 'Dispatch plan'

  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start', margin: '5px 0 7px' }}>
      <div
        style={{
          width: '100%',
          maxWidth: '80%',
          background: '#0e131e',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 14,
          overflow: 'hidden',
          boxShadow: '0 2px 14px rgba(0,0,0,0.3)',
        }}
      >
        {/* Header — click toggles the whole card */}
        <div
          onClick={onToggleMain}
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '12px 15px',
            cursor: 'pointer',
            userSelect: 'none',
            background: mainOpen ? 'rgba(255,255,255,0.02)' : 'transparent',
            borderBottom: mainOpen ? '1px solid rgba(255,255,255,0.06)' : '1px solid transparent',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <span style={{ width: 20, height: 20, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
              {hasActive ? (
                <Spinner stroke={accent} />
              ) : allSuccess ? (
                <Check stroke="#4ade80" sw={2.4} />
              ) : (
                <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="#9aa0b4" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                  <path d="M13 2 3 14h7v8l10-12h-7z" />
                </svg>
              )}
            </span>
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14, letterSpacing: '0.01em', color: '#eef0f6' }}>{planTitle}</span>
          </div>
          <Chevron size={16} rotated={!mainOpen} />
        </div>

        {/* Body — CSS-grid 0fr↔1fr collapse */}
        <div
          style={{
            display: 'grid',
            gridTemplateRows: mainOpen ? '1fr' : '0fr',
            opacity: mainOpen ? 1 : 0,
            transition: 'grid-template-rows 0.42s cubic-bezier(0.16,1,0.3,1), opacity 0.42s',
          }}
        >
          <div style={{ overflow: 'hidden' }}>
            <div style={{ padding: '17px 18px 4px', display: 'flex', flexDirection: 'column' }}>
              {steps.map((step, idx) => {
                const key = `${msgId}/${step.id}`
                const open = stepOpen[key] !== undefined ? stepOpen[key] : !!step.defaultExpanded
                const meta = planStatusMeta(step.status, accent)
                const hasDetail = !!step.detail
                const d = step.detail
                return (
                  <div key={step.id} style={{ position: 'relative', display: 'flex', gap: 14, opacity: step.status === 'pending' ? 0.5 : 1 }}>
                    {idx < steps.length - 1 && (
                      <div style={{ position: 'absolute', left: 11, top: 28, bottom: -8, width: 2, background: 'rgba(255,255,255,0.09)', zIndex: 0 }} />
                    )}
                    {/* Ring */}
                    <div style={{ position: 'relative', zIndex: 1, flex: 'none', width: 24, height: 24, marginTop: 1 }}>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: '100%',
                          height: '100%',
                          borderRadius: '50%',
                          boxShadow: '0 0 0 4px #0e131e',
                          background: meta.ringBg,
                          color: meta.ringColor,
                        }}
                      >
                        <StepNode step={step} ringColor={meta.ringColor} />
                      </div>
                    </div>
                    {/* Title + detail */}
                    <div style={{ flex: 1, minWidth: 0, paddingBottom: 18 }}>
                      <div
                        onClick={hasDetail ? () => onToggleStep(key) : undefined}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 10,
                          cursor: hasDetail ? 'pointer' : 'default',
                          borderRadius: 7,
                          margin: '0 -6px',
                          padding: '2px 6px',
                        }}
                        onMouseEnter={(e) => hasDetail && (e.currentTarget.style.background = 'rgba(255,255,255,0.03)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                      >
                        <span
                          style={{
                            fontSize: 13.5,
                            letterSpacing: '0.01em',
                            color: step.status === 'active' ? '#f0f2f8' : step.status === 'error' ? '#fb6f6f' : '#c6cad8',
                            fontWeight: step.status === 'active' || step.status === 'error' ? 600 : 500,
                          }}
                        >
                          {step.title}
                        </span>
                        <span style={{ flex: 'none', display: 'flex', alignItems: 'center', gap: 10 }}>
                          {step.duration && (
                            <span className="mono" style={{ fontSize: 11, color: '#6a7088' }}>
                              {step.duration}
                            </span>
                          )}
                          {hasDetail && <Chevron rotated={!open} />}
                        </span>
                      </div>
                      {hasDetail && d && (
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateRows: open ? '1fr' : '0fr',
                            opacity: open ? 1 : 0,
                            marginTop: open ? 8 : 0,
                            transition: 'grid-template-rows 0.34s ease, opacity 0.34s, margin-top 0.34s',
                          }}
                        >
                          <div style={{ overflow: 'hidden' }}>
                            {d.lead && (
                              <div
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 7,
                                  fontFamily: 'var(--font-mono)',
                                  fontSize: 11,
                                  fontWeight: 500,
                                  color: d.lead.color,
                                  marginBottom: 8,
                                }}
                              >
                                {d.lead.kind === 'spinner' ? <Spinner size={13} stroke="currentColor" /> : <Check size={13} stroke="currentColor" sw={2.6} />}
                                <span>{d.lead.text}</span>
                              </div>
                            )}
                            <div
                              style={{
                                background: d.boxBg,
                                border: `1px solid ${d.boxBorder}`,
                                borderRadius: 9,
                                padding: '11px 13px',
                                fontFamily: 'var(--font-mono)',
                                fontSize: 11,
                                lineHeight: 1.75,
                              }}
                            >
                              {d.lines.map((ln, li) =>
                                ln.label !== undefined ? (
                                  <div key={li} style={{ display: 'grid', gridTemplateColumns: '84px 1fr', gap: 10, padding: '1px 0' }}>
                                    <span style={{ color: '#6a7088' }}>{ln.label}</span>
                                    <span style={{ color: ln.valueColor || '#d4d8e4' }}>{ln.value}</span>
                                  </div>
                                ) : (
                                  <div key={li} style={{ color: ln.color || '#9298ab', paddingLeft: ln.indent || 0 }}>
                                    {ln.text}
                                  </div>
                                ),
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
