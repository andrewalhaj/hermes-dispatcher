import { useEffect, useRef, useState } from 'react'
import { ACCENT } from '../../data/agents'
import { ACCENT_SWATCHES, API_KEYS, LANG_OPTS, MODEL_OPTS, SETTINGS_TOGGLES } from '../../data/phase3'
import '../../styles/phase3.css'

interface SettingsProps {
  accent?: string
  /** Lift accent changes to the Shell so --ac updates globally. When omitted,
   *  the panel falls back to setting --ac on document.documentElement. */
  onAccentChange?: (color: string) => void
}

const sectionStyle: React.CSSProperties = { background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 12, padding: '4px 18px' }
const sectionLabel: React.CSSProperties = { fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6a7088', margin: '16px 0 4px' }
const rowStyle: React.CSSProperties = { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 18, padding: '14px 0' }
const rowTopBorder: React.CSSProperties = { ...rowStyle, borderTop: '1px solid rgba(255,255,255,0.05)' }
const rowTitle: React.CSSProperties = { fontSize: 13.5, color: '#e4e6ee' }
const rowDesc: React.CSSProperties = { fontSize: 12, color: 'var(--text-muted)', marginTop: 3 }
const selectStyle: React.CSSProperties = { background: 'var(--s4)', color: '#cdd2e0', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 11px', fontSize: 12.5, fontFamily: 'inherit', outline: 'none', cursor: 'pointer' }

function Toggle({ on, onClick, accent }: { on: boolean; onClick: () => void; accent: string }) {
  return (
    <button onClick={onClick} className="relative flex-none" style={{ width: 38, height: 22, borderRadius: 12, border: 'none', background: on ? accent : 'rgba(255,255,255,0.12)', cursor: 'pointer', transition: 'background 0.15s' }}>
      <span style={{ position: 'absolute', top: 2, left: on ? 18 : 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', transition: 'left 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.4)' }} />
    </button>
  )
}

function Segmented({ value, options, onChange, accent }: { value: string; options: { label: string; value: string }[]; onChange: (v: string) => void; accent: string }) {
  return (
    <div className="flex" style={{ gap: 6 }}>
      {options.map((o) => {
        const on = value === o.value
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            style={{ background: on ? `color-mix(in oklab, ${accent} 16%, transparent)` : 'var(--s4)', color: on ? '#f0f2f8' : 'var(--text-muted)', border: `1px solid ${on ? `color-mix(in oklab, ${accent} 45%, transparent)` : 'rgba(255,255,255,0.1)'}`, borderRadius: 8, padding: '7px 13px', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer' }}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

function Toast({ msg, accent }: { msg: string; accent: string }) {
  const isErr = msg.toLowerCase().includes('error')
  return (
    <div style={{
      position: 'fixed', bottom: 32, right: 32, zIndex: 9999,
      background: isErr ? '#2a1a1a' : '#141924',
      border: `1px solid ${isErr ? '#fb6f6f' : accent}`,
      color: isErr ? '#fb6f6f' : '#e4e6ee',
      borderRadius: 10, padding: '10px 18px', fontSize: 13,
      boxShadow: `0 4px 24px rgba(0,0,0,0.5)`,
      animation: 'hpanelin 0.25s var(--ease-out)',
    }}>
      {msg}
    </div>
  )
}

export default function Settings({ accent = ACCENT, onAccentChange }: SettingsProps) {
  const [toggles, setToggles] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(SETTINGS_TOGGLES.map((t) => [t.key, t.default])),
  )
  const [theme, setTheme] = useState('dark')
  const [reason, setReason] = useState('xhigh')
  const [lang, setLang] = useState('en')
  const [model, setModel] = useState(MODEL_OPTS[0])
  const [modelOpts, setModelOpts] = useState<string[]>(MODEL_OPTS)
  const [ws, setWs] = useState('~/projects/dm-voice-board')
  const [botName, setBotName] = useState('Hermes')
  const [revealed, setReveal] = useState<Record<number, boolean>>({})
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const showToast = (msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast(msg)
    toastTimer.current = setTimeout(() => setToast(null), 2500)
  }

  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((d) => {
        if (d.model?.default) setModel(d.model.default)
        if (d.display?.language) setLang(d.display.language)
        if (d.reasoning_effort) setReason(d.reasoning_effort)
        if (typeof d.display?.streaming === 'boolean') {
          setToggles((p) => ({ ...p, setStream: d.display.streaming }))
        }
        if (typeof d.display?.show_cost === 'boolean') {
          setToggles((p) => ({ ...p, setInsights: d.display.show_cost }))
        }
      })
      .catch(() => {})

    fetch('/api/settings/models')
      .then((r) => r.json())
      .then((d) => {
        if (Array.isArray(d.models) && d.models.length > 0) setModelOpts(d.models)
      })
      .catch(() => {})

    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current)
    }
  }, [])

  const pickAccent = (c: string) => {
    if (onAccentChange) onAccentChange(c)
    else document.documentElement.style.setProperty('--ac', c)
  }

  const handleSave = async () => {
    try {
      const body = {
        model: { default: model },
        display: {
          language: lang,
          streaming: toggles['setStream'] ?? true,
          show_cost: toggles['setInsights'] ?? false,
        },
        reasoning_effort: reason,
      }
      const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const json = await res.json()
      if (res.ok && json.ok) {
        showToast('Saved')
      } else {
        showToast('Error saving')
      }
    } catch {
      showToast('Error saving')
    }
  }

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Settings</div>
          <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>appearance &amp; behavior</div>
        </div>
        <button
          onClick={handleSave}
          style={{
            background: `color-mix(in oklab, ${accent} 18%, transparent)`,
            color: '#e4e6ee',
            border: `1px solid color-mix(in oklab, ${accent} 45%, transparent)`,
            borderRadius: 9,
            padding: '8px 20px',
            fontSize: 13,
            fontFamily: 'inherit',
            cursor: 'pointer',
            fontWeight: 500,
            transition: 'background 0.15s',
          }}
          onMouseEnter={(e) => { e.currentTarget.style.background = `color-mix(in oklab, ${accent} 28%, transparent)` }}
          onMouseLeave={(e) => { e.currentTarget.style.background = `color-mix(in oklab, ${accent} 18%, transparent)` }}
        >
          Save
        </button>
      </header>
      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '24px 26px 40px' }}>
        <div style={{ maxWidth: 720, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18, animation: 'hpanelin 0.4s var(--ease-out)' }}>
          {/* Appearance */}
          <div style={sectionStyle}>
            <div style={sectionLabel}>Appearance</div>
            <div style={rowStyle}>
              <div>
                <div style={rowTitle}>Theme</div>
                <div style={rowDesc}>Light, dark, or follow the system.</div>
              </div>
              <Segmented value={theme} onChange={setTheme} accent={accent} options={[{ label: 'System', value: 'system' }, { label: 'Light', value: 'light' }, { label: 'Dark', value: 'dark' }]} />
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Accent color</div>
                <div style={rowDesc}>Drives glow, active states, and the dispatcher pulse.</div>
              </div>
              <div className="flex" style={{ gap: 9 }}>
                {ACCENT_SWATCHES.map((c) => (
                  <button
                    key={c}
                    onClick={() => pickAccent(c)}
                    aria-label={`Accent ${c}`}
                    style={{ width: 24, height: 24, borderRadius: '50%', background: c, border: 'none', boxShadow: `0 0 0 2px ${c === accent ? c : 'transparent'}`, cursor: 'pointer', transition: 'box-shadow 0.15s' }}
                  />
                ))}
              </div>
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Language</div>
                <div style={rowDesc}>Interface language.</div>
              </div>
              <select value={lang} onChange={(e) => setLang(e.target.value)} style={selectStyle}>
                {LANG_OPTS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Agent defaults */}
          <div style={sectionStyle}>
            <div style={sectionLabel}>Agent defaults</div>
            <div style={rowStyle}>
              <div>
                <div style={rowTitle}>Assistant name</div>
                <div style={rowDesc}>How the agent refers to itself.</div>
              </div>
              <input value={botName} onChange={(e) => setBotName(e.target.value)} style={{ width: 180, background: 'var(--s4)', color: '#e9ebf2', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 11px', fontSize: 12.5, fontFamily: 'inherit', outline: 'none' }} onFocus={(e) => (e.currentTarget.style.borderColor = accent)} onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')} />
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Default model</div>
                <div style={rowDesc}>Model new sessions start with.</div>
              </div>
              <select value={model} onChange={(e) => setModel(e.target.value)} style={{ ...selectStyle, maxWidth: 200 }}>
                {modelOpts.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Default workspace</div>
                <div style={rowDesc}>Working directory for new runs.</div>
              </div>
              <input value={ws} onChange={(e) => setWs(e.target.value)} className="mono" style={{ width: 200, background: 'var(--s4)', color: '#e9ebf2', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 11px', fontSize: 12, outline: 'none' }} onFocus={(e) => (e.currentTarget.style.borderColor = accent)} onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')} />
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Reasoning effort</div>
                <div style={rowDesc}>Default thinking budget per turn.</div>
              </div>
              <Segmented value={reason} onChange={setReason} accent={accent} options={[{ label: 'Low', value: 'low' }, { label: 'Medium', value: 'medium' }, { label: 'High', value: 'high' }, { label: 'xHigh', value: 'xhigh' }]} />
            </div>
          </div>

          {/* Behavior toggles */}
          <div style={sectionStyle}>
            <div style={sectionLabel}>Behavior</div>
            {SETTINGS_TOGGLES.map((t, i) => (
              <div key={t.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 0', borderTop: i === 0 ? undefined : '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ paddingRight: 18 }}>
                  <div style={rowTitle}>{t.label}</div>
                  <div style={rowDesc}>{t.desc}</div>
                </div>
                <Toggle on={toggles[t.key]} accent={accent} onClick={() => setToggles((p) => ({ ...p, [t.key]: !p[t.key] }))} />
              </div>
            ))}
          </div>

          {/* API keys */}
          <div style={sectionStyle}>
            <div style={sectionLabel}>API keys</div>
            {API_KEYS.map((k, i) => (
              <div key={k.label} style={i === 0 ? rowStyle : rowTopBorder}>
                <div>
                  <div style={rowTitle}>{k.label}</div>
                  <div style={rowDesc}>Used for outbound model and tool calls.</div>
                </div>
                <div className="flex items-center" style={{ gap: 8 }}>
                  <input
                    readOnly
                    type={revealed[i] ? 'text' : 'password'}
                    value={k.value}
                    className="mono"
                    style={{ width: 168, background: 'var(--s4)', color: '#9aa0b4', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 11px', fontSize: 12, outline: 'none' }}
                  />
                  <button onClick={() => setReveal((p) => ({ ...p, [i]: !p[i] }))} style={{ background: 'var(--s4)', color: '#c6cad8', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 12px', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer' }}>
                    {revealed[i] ? 'Hide' : 'Reveal'}
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* About */}
          <div style={sectionStyle}>
            <div style={sectionLabel}>About</div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 0' }}>
              <span style={{ fontSize: 13, color: '#c6cad8' }}>WebUI version</span>
              <span className="mono" style={{ fontSize: 12, color: 'var(--text-muted)' }}>v2.0.0</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 0', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ fontSize: 13, color: '#c6cad8' }}>Host</span>
              <span className="mono" style={{ fontSize: 12, color: 'var(--text-muted)' }}>localhost · encrypted</span>
            </div>
          </div>
        </div>
      </div>
      {toast && <Toast msg={toast} accent={accent} />}
    </div>
  )
}
