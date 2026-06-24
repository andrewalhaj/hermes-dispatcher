import { useEffect, useRef, useState } from 'react'
import { ACCENT } from '../../data/agents'
import { ACCENT_SWATCHES, API_KEYS, LANG_OPTS, MODEL_OPTS, SETTINGS_TOGGLES } from '../../data/phase3'
import { lsGet, lsGetJson, lsSet } from '../../utils/localStorage'
import '../../styles/phase3.css'

interface SettingsProps {
  accent?: string
  /** Lift accent changes to the Shell so --ac updates globally. When omitted,
   *  the panel falls back to setting --ac on document.documentElement. */
  onAccentChange?: (color: string) => void
}

// localStorage key constants
const LS_THEME = 'hermes-settings-theme'
const LS_LANG = 'hermes-settings-lang'
const LS_MODEL = 'hermes-settings-model'
const LS_REASON = 'hermes-settings-reason'
const LS_BOTNAME = 'hermes-settings-botName'
const LS_WS = 'hermes-settings-ws'
const LS_TOGGLES = 'hermes-settings-toggles'

const sectionStyle: React.CSSProperties = { background: 'var(--s3)', border: '1px solid var(--tile-border)', borderRadius: 12, padding: '4px 18px' }
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
  // Seed from localStorage for instant restore on remount; backend reconciles after mount
  const [toggles, setToggles] = useState<Record<string, boolean>>(() =>
    lsGetJson(LS_TOGGLES, Object.fromEntries(SETTINGS_TOGGLES.map((t) => [t.key, t.default]))),
  )
  const [theme, setTheme] = useState(() => lsGet(LS_THEME, 'dark'))
  const [reason, setReason] = useState(() => lsGet(LS_REASON, 'xhigh'))
  const [lang, setLang] = useState(() => lsGet(LS_LANG, 'en'))
  const [model, setModel] = useState(() => lsGet(LS_MODEL, MODEL_OPTS[0]))
  const [modelOpts, setModelOpts] = useState<string[]>(MODEL_OPTS)
  const [ws, setWs] = useState(() => lsGet(LS_WS, '~/projects/dm-voice-board'))
  const [botName, setBotName] = useState(() => lsGet(LS_BOTNAME, 'Hermes'))
  const [revealed, setReveal] = useState<Record<number, boolean>>({})
  const [toast, setToast] = useState<string | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const textDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Always-fresh ref so debounced callbacks see current state
  const stateRef = useRef({ theme, lang, model, reason, botName, ws, toggles })
  stateRef.current = { theme, lang, model, reason, botName, ws, toggles }

  const showToast = (msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast(msg)
    toastTimer.current = setTimeout(() => setToast(null), 2500)
  }

  const doPut = (body: object) => {
    fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).catch(() => { /* localStorage already updated; backend sync is best-effort */ })
  }

  type Overrides = {
    theme?: string; lang?: string; model?: string; reason?: string
    botName?: string; ws?: string; toggles?: Record<string, boolean>
  }

  const buildBody = (overrides: Overrides = {}) => {
    const t = overrides.toggles ?? toggles
    return {
      model: { default: overrides.model ?? model },
      display: {
        theme: overrides.theme ?? theme,
        language: overrides.lang ?? lang,
        streaming: t['setStream'] ?? true,
        show_cost: t['setInsights'] ?? false,
      },
      reasoning_effort: overrides.reason ?? reason,
      agent: {
        name: overrides.botName ?? botName,
        workspace: overrides.ws ?? ws,
      },
      dashboard: t,
    }
  }

  /** Immediate persist — for dropdowns, segmented controls, toggles. */
  const persist = (overrides: Overrides) => {
    if (overrides.theme !== undefined) lsSet(LS_THEME, overrides.theme)
    if (overrides.lang !== undefined) lsSet(LS_LANG, overrides.lang)
    if (overrides.model !== undefined) lsSet(LS_MODEL, overrides.model)
    if (overrides.reason !== undefined) lsSet(LS_REASON, overrides.reason)
    if (overrides.botName !== undefined) lsSet(LS_BOTNAME, overrides.botName)
    if (overrides.ws !== undefined) lsSet(LS_WS, overrides.ws)
    if (overrides.toggles !== undefined) lsSet(LS_TOGGLES, JSON.stringify(overrides.toggles))
    doPut(buildBody(overrides))
  }

  /** Debounced persist (600 ms) — for text inputs. Uses stateRef for latest values. */
  const persistDebounced = (textOverrides: { botName?: string; ws?: string }) => {
    if (textDebounceRef.current) clearTimeout(textDebounceRef.current)
    if (textOverrides.botName !== undefined) lsSet(LS_BOTNAME, textOverrides.botName)
    if (textOverrides.ws !== undefined) lsSet(LS_WS, textOverrides.ws)
    textDebounceRef.current = setTimeout(() => {
      const s = stateRef.current
      const t = s.toggles
      doPut({
        model: { default: s.model },
        display: { theme: s.theme, language: s.lang, streaming: t['setStream'] ?? true, show_cost: t['setInsights'] ?? false },
        reasoning_effort: s.reason,
        agent: { name: textOverrides.botName ?? s.botName, workspace: textOverrides.ws ?? s.ws },
        dashboard: t,
      })
    }, 600)
  }

  useEffect(() => {
    fetch('/api/settings')
      .then((r) => r.json())
      .then((d) => {
        // Backend is source of truth — reconcile and update localStorage
        if (d.model?.default) { setModel(d.model.default); lsSet(LS_MODEL, d.model.default) }
        if (d.display?.language) { setLang(d.display.language); lsSet(LS_LANG, d.display.language) }
        if (d.display?.theme) { setTheme(d.display.theme); lsSet(LS_THEME, d.display.theme) }
        if (d.reasoning_effort) { setReason(d.reasoning_effort); lsSet(LS_REASON, d.reasoning_effort) }
        if (d.agent?.name) { setBotName(d.agent.name); lsSet(LS_BOTNAME, d.agent.name) }
        if (d.agent?.workspace) { setWs(d.agent.workspace); lsSet(LS_WS, d.agent.workspace) }
        // Merge dashboard toggles; also handle legacy display.streaming/show_cost
        const merged: Record<string, boolean> = {}
        if (typeof d.display?.streaming === 'boolean') merged['setStream'] = d.display.streaming
        if (typeof d.display?.show_cost === 'boolean') merged['setInsights'] = d.display.show_cost
        for (const [k, v] of Object.entries(d.dashboard ?? {})) {
          if (typeof v === 'boolean') merged[k] = v
        }
        if (Object.keys(merged).length > 0) {
          setToggles((p) => {
            const next = { ...p, ...merged }
            lsSet(LS_TOGGLES, JSON.stringify(next))
            return next
          })
        }
      })
      .catch(() => { /* keep localStorage values if backend unreachable */ })

    fetch('/api/settings/models')
      .then((r) => r.json())
      .then((d) => {
        if (Array.isArray(d.models) && d.models.length > 0) setModelOpts(d.models)
      })
      .catch(() => {})

    return () => {
      if (toastTimer.current) clearTimeout(toastTimer.current)
      if (textDebounceRef.current) clearTimeout(textDebounceRef.current)
    }
  }, [])

  const pickAccent = (c: string) => {
    lsSet('hermes-accent', c)
    if (onAccentChange) onAccentChange(c)
    else document.documentElement.style.setProperty('--ac', c)
  }

  const handleSave = async () => {
    try {
      const res = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBody()),
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
          <div style={{ ...sectionStyle, animation: 'hcellin 0.45s ease backwards', animationDelay: '0s' }}>
            <div style={sectionLabel}>Appearance</div>
            <div style={rowStyle}>
              <div>
                <div style={rowTitle}>Theme</div>
                <div style={rowDesc}>Light, dark, or follow the system.</div>
              </div>
              <Segmented value={theme} accent={accent} options={[{ label: 'System', value: 'system' }, { label: 'Light', value: 'light' }, { label: 'Dark', value: 'dark' }]} onChange={(v) => { setTheme(v); persist({ theme: v }) }} />
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Accent color</div>
                <div style={rowDesc}>Drives glow, active states, and the dispatcher pulse.</div>
              </div>
              <div className="flex" style={{ gap: 9 }}>
                {ACCENT_SWATCHES.map((c) => {
                  const isSelected = c === accent
                  return (
                    <button
                      key={c}
                      onClick={() => pickAccent(c)}
                      aria-label={`Accent ${c}`}
                      aria-pressed={isSelected}
                      style={{ width: 24, height: 24, borderRadius: '50%', background: c, border: 'none', boxShadow: isSelected ? '0 0 0 2px var(--s3), 0 0 0 4px #fff' : 'none', cursor: 'pointer', transition: 'box-shadow 0.15s' }}
                    />
                  )
                })}
              </div>
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Language</div>
                <div style={rowDesc}>Interface language.</div>
              </div>
              <select value={lang} style={selectStyle} onChange={(e) => { setLang(e.target.value); persist({ lang: e.target.value }) }}>
                {LANG_OPTS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Agent defaults */}
          <div style={{ ...sectionStyle, animation: 'hcellin 0.45s ease backwards', animationDelay: '0.07s' }}>
            <div style={sectionLabel}>Agent defaults</div>
            <div style={rowStyle}>
              <div>
                <div style={rowTitle}>Assistant name</div>
                <div style={rowDesc}>How the agent refers to itself.</div>
              </div>
              <input value={botName} style={{ width: 180, background: 'var(--s4)', color: '#e9ebf2', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 11px', fontSize: 12.5, fontFamily: 'inherit', outline: 'none' }} onChange={(e) => { setBotName(e.target.value); persistDebounced({ botName: e.target.value }) }} onFocus={(e) => (e.currentTarget.style.borderColor = accent)} onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')} />
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Default model</div>
                <div style={rowDesc}>Model new sessions start with.</div>
              </div>
              <select value={model} style={{ ...selectStyle, maxWidth: 200 }} onChange={(e) => { setModel(e.target.value); persist({ model: e.target.value }) }}>
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
              <input value={ws} title={ws} className="mono" style={{ width: 200, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', background: 'var(--s4)', color: '#e9ebf2', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '8px 11px', fontSize: 12, outline: 'none' }} onChange={(e) => { setWs(e.target.value); persistDebounced({ ws: e.target.value }) }} onFocus={(e) => (e.currentTarget.style.borderColor = accent)} onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')} />
            </div>
            <div style={rowTopBorder}>
              <div>
                <div style={rowTitle}>Reasoning effort</div>
                <div style={rowDesc}>Default thinking budget per turn.</div>
              </div>
              <Segmented value={reason} accent={accent} options={[{ label: 'Low', value: 'low' }, { label: 'Medium', value: 'medium' }, { label: 'High', value: 'high' }, { label: 'xHigh', value: 'xhigh' }]} onChange={(v) => { setReason(v); persist({ reason: v }) }} />
            </div>
          </div>

          {/* Behavior toggles */}
          <div style={{ ...sectionStyle, animation: 'hcellin 0.45s ease backwards', animationDelay: '0.14s' }}>
            <div style={sectionLabel}>Behavior</div>
            {SETTINGS_TOGGLES.map((t, i) => (
              <div key={t.key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 0', borderTop: i === 0 ? undefined : '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ paddingRight: 18 }}>
                  <div style={rowTitle}>{t.label}</div>
                  <div style={rowDesc}>{t.desc}</div>
                </div>
                <Toggle on={toggles[t.key]} accent={accent} onClick={() => {
                  const next = { ...toggles, [t.key]: !toggles[t.key] }
                  setToggles(next)
                  persist({ toggles: next })
                }} />
              </div>
            ))}
          </div>

          {/* API keys */}
          <div style={{ ...sectionStyle, animation: 'hcellin 0.45s ease backwards', animationDelay: '0.21s' }}>
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
          <div style={{ ...sectionStyle, animation: 'hcellin 0.45s ease backwards', animationDelay: '0.28s' }}>
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
