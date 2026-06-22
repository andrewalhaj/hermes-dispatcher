import { useEffect, useRef, useState } from 'react'
import { CHAT_AGENTS } from '../../data/agents'
import {
  FOLDER_OPTIONS,
  INITIAL_THREADS,
  MODEL_OPTIONS,
  PAST_SESSIONS,
  PROFILE_OPTIONS,
  REASON_OPTIONS,
  cannedReply,
  epochToWhen,
  nowTime,
} from '../../data/chat'
import type { ChatAgent, Message, PastSession } from '../../data/types'
import ComposerDropdown from '../chat/ComposerDropdown'
import PlanBlock from '../chat/PlanBlock'
import { COMMANDS } from '../../data/commands'

declare global {
  interface Window {
    SpeechRecognition?: any
    webkitSpeechRecognition?: any
    mermaid?: any
    Prism?: any
  }
}

// ── Text segment parser ──────────────────────────────────────────────────────

type Segment =
  | { type: 'text'; content: string }
  | { type: 'mermaid'; content: string }
  | { type: 'code'; lang: string; content: string }

function parseMessageText(text: string): Segment[] {
  const segs: Segment[] = []
  const re = /```(\w*)\n([\s\S]*?)```/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) segs.push({ type: 'text', content: text.slice(last, m.index) })
    const lang = m[1].toLowerCase()
    if (lang === 'mermaid') {
      segs.push({ type: 'mermaid', content: m[2] })
    } else {
      segs.push({ type: 'code', lang: lang || 'text', content: m[2] })
    }
    last = m.index + m[0].length
  }
  if (last < text.length) segs.push({ type: 'text', content: text.slice(last) })
  return segs
}

// ── Mermaid block ────────────────────────────────────────────────────────────

let _mermaidInited = false
function ensureMermaidInit() {
  if (_mermaidInited || !window.mermaid) return
  window.mermaid.initialize({ startOnLoad: false, theme: 'dark' })
  _mermaidInited = true
}

function MermaidBlock({ content }: { content: string }) {
  const [svg, setSvg] = useState<string | null>(null)
  const [err, setErr] = useState(false)
  const idRef = useRef('mmd-' + Math.random().toString(36).slice(2))

  useEffect(() => {
    if (!window.mermaid) { setErr(true); return }
    ensureMermaidInit()
    window.mermaid
      .render(idRef.current, content)
      .then((r: { svg: string }) => setSvg(r.svg))
      .catch(() => setErr(true))
  }, [content])

  if (err) {
    return (
      <pre style={{ margin: '6px 0', padding: '10px 14px', background: 'rgba(0,0,0,0.35)', borderRadius: 8, fontSize: 12.5, overflowX: 'auto', color: '#d8dbe6' }}>
        {content}
      </pre>
    )
  }
  if (!svg) {
    return <div style={{ fontSize: 12, color: '#6a7088', padding: '4px 0' }}>Rendering diagram…</div>
  }
  return <div dangerouslySetInnerHTML={{ __html: svg }} style={{ maxWidth: '100%', overflowX: 'auto', margin: '6px 0' }} />
}

// ── Code block with Prism + copy ─────────────────────────────────────────────

function CodeBlock({ lang, content }: { lang: string; content: string }) {
  const codeRef = useRef<HTMLElement>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (window.Prism && codeRef.current) {
      window.Prism.highlightElement(codeRef.current)
    }
  }, [content])

  function copy() {
    navigator.clipboard.writeText(content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    })
  }

  return (
    <div style={{ position: 'relative', margin: '6px 0' }}>
      <pre style={{ margin: 0, padding: '10px 44px 10px 14px', background: 'rgba(0,0,0,0.4)', borderRadius: 8, overflowX: 'auto', fontSize: 12.5, lineHeight: 1.5 }}>
        <code ref={codeRef} className={`language-${lang}`} style={{ fontFamily: 'IBM Plex Mono, monospace' }}>
          {content}
        </code>
      </pre>
      <button
        onClick={copy}
        style={{
          position: 'absolute', top: 6, right: 6,
          background: copied ? 'rgba(74,222,128,0.15)' : 'rgba(255,255,255,0.08)',
          border: `1px solid ${copied ? 'rgba(74,222,128,0.3)' : 'rgba(255,255,255,0.12)'}`,
          color: copied ? '#4ade80' : '#9298ab',
          borderRadius: 6, padding: '3px 9px', fontSize: 11, fontFamily: 'inherit', cursor: 'pointer',
          transition: 'all 0.2s',
        }}
      >
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

// ── Message content renderer ─────────────────────────────────────────────────

function MessageContent({ text }: { text: string }) {
  const segs = parseMessageText(text)
  return (
    <>
      {segs.map((seg, i) => {
        if (seg.type === 'mermaid') return <MermaidBlock key={i} content={seg.content} />
        if (seg.type === 'code') return <CodeBlock key={i} lang={seg.lang} content={seg.content} />
        return (
          <span key={i} style={{ fontSize: 14, lineHeight: 1.55, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
            {seg.content}
          </span>
        )
      })}
    </>
  )
}

interface ChatProps {
  accent: string
}

const clone = <T,>(o: T): T => JSON.parse(JSON.stringify(o)) as T

export default function Chat({ accent }: ChatProps) {
  const [activeAgent, setActiveAgent] = useState('hermes')
  const [threads, setThreads] = useState<Record<string, Message[]>>(() => clone(INITIAL_THREADS))
  const [draft, setDraft] = useState('')
  const [running, setRunning] = useState(false)
  const [agentMenu, setAgentMenu] = useState(false)
  const [histOpen, setHistOpen] = useState(false)
  const [viewSession, setViewSession] = useState<PastSession | null>(null)
  const [composerMenu, setComposerMenu] = useState<string | null>(null)
  const [profile, setProfile] = useState('default')
  const [folder, setFolder] = useState('Home')
  const [model, setModel] = useState('Claude Sonnet 4.6')
  const [reason, setReason] = useState('xhigh')
  const [planMainOpen, setPlanMainOpen] = useState<Record<string, boolean>>({})
  const [planStepOpen, setPlanStepOpen] = useState<Record<string, boolean>>({})

  // Voice input
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef<any>(null)
  const silenceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const baseDraftRef = useRef('')
  const hasSpeech = !!(window.SpeechRecognition || window.webkitSpeechRecognition)

  // Slash commands
  const [cmdOpen, setCmdOpen] = useState(false)
  const [cmdIdx, setCmdIdx] = useState(0)
  const filteredCmds = cmdOpen
    ? COMMANDS.filter(c => draft.length <= 1 || c.cmd.startsWith(draft.toLowerCase().split(' ')[0]))
    : []

  const [sessionId] = useState(() => crypto.randomUUID())
  const [profileOpts, setProfileOpts] = useState<string[]>(PROFILE_OPTIONS)
  const [modelOpts, setModelOpts] = useState<string[]>(MODEL_OPTIONS)
  const [hermesSessions, setHermesSessions] = useState<PastSession[] | null>(null)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const agent = CHAT_AGENTS.find((a) => a.key === activeAgent) || CHAT_AGENTS[0]
  const thread = threads[activeAgent] || []
  const displayThread = viewSession ? viewSession.msgs.map((m, i) => ({ id: `v${i}`, ...m })) : thread
  const pastList = activeAgent === 'hermes' && hermesSessions ? hermesSessions : (PAST_SESSIONS[activeAgent] || [])
  const ctxChars = thread.reduce((n, m) => n + m.text.length, 0)
  const ctxNum = Math.min(99, Math.round(ctxChars / 28))
  const ringDash = `${((Math.min(100, Math.round(ctxChars / 28)) / 100) * 56.55).toFixed(1)} 56.55`
  const todayStr = new Date().toDateString()

  useEffect(() => {
    if (viewSession) return
    const el = listRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [thread.length, running, viewSession])

  useEffect(() => {
    ;(async () => {
      try {
        const res = await fetch('/api/profiles')
        const data = await res.json() as string[]
        setProfileOpts(data)
      } catch { /* keep fallback */ }

      try {
        const res = await fetch('/api/models')
        const data = await res.json() as { default: string; catalog: string[] }
        setModelOpts(data.catalog)
        setModel(data.default)
      } catch { /* keep fallback */ }

      try {
        const res = await fetch('/api/chat/sessions')
        const data = await res.json() as { id: string; title: string; created_at: number }[]
        setHermesSessions(data.map((s) => ({ id: s.id, title: s.title, when: epochToWhen(s.created_at), msgs: [] })))
      } catch {
        setHermesSessions([])
      }
    })()
  }, [])

  useEffect(() => () => {
    abortRef.current?.abort()
    if (timerRef.current) clearTimeout(timerRef.current)
    recognitionRef.current?.stop()
    if (silenceRef.current) clearTimeout(silenceRef.current)
  }, [])

  function selectAgent(key: string) {
    setActiveAgent(key)
    setAgentMenu(false)
    setViewSession(null)
  }

  function toggleVoice() {
    if (listening) {
      recognitionRef.current?.stop()
      recognitionRef.current = null
      setListening(false)
      if (silenceRef.current) clearTimeout(silenceRef.current)
      return
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return
    baseDraftRef.current = draft
    const rec = new SR()
    rec.continuous = true
    rec.interimResults = true
    rec.onresult = (e: any) => {
      if (silenceRef.current) clearTimeout(silenceRef.current)
      let interim = ''
      let finalChunk = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalChunk += e.results[i][0].transcript
        else interim += e.results[i][0].transcript
      }
      if (finalChunk) {
        baseDraftRef.current = (baseDraftRef.current + ' ' + finalChunk).trim()
        setDraft(baseDraftRef.current)
      } else if (interim) {
        setDraft((baseDraftRef.current + ' ' + interim).trim())
      }
      silenceRef.current = setTimeout(() => { rec.stop() }, 2000)
    }
    rec.onerror = () => { setListening(false); recognitionRef.current = null }
    rec.onend = () => {
      setListening(false)
      recognitionRef.current = null
      if (silenceRef.current) clearTimeout(silenceRef.current)
    }
    recognitionRef.current = rec
    rec.start()
    setListening(true)
  }

  async function send() {
    const t = draft.trim()
    if (!t || running) return
    setCmdOpen(false)

    if (t === '/clear') {
      setThreads((s) => ({ ...s, [activeAgent]: [] }))
      setDraft('')
      return
    }
    if (t === '/new') {
      setThreads((s) => ({ ...s, [activeAgent]: [] }))
      setViewSession(null)
      setDraft('')
      return
    }

    const k = activeAgent
    const at = nowTime()
    if (k === 'hermes') {
      setThreads((s) => ({ ...s, [k]: [...(s[k] || []), { id: 'u' + Date.now(), role: 'user', text: t, at }] }))
      setDraft('')
      setRunning(true)
      const controller = new AbortController()
      abortRef.current = controller
      let agentMsgId: string | null = null
      try {
        const res = await fetch('/api/chat/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message: t, profile, model }),
          signal: controller.signal,
        })
        const reader = res.body!.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        outer: while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split('\n\n')
          buffer = parts.pop() ?? ''
          for (const chunk of parts) {
            if (!chunk.startsWith('data:')) continue
            const ev = JSON.parse(chunk.slice(5).trim()) as { type: string; text: string }
            if (ev.type === 'delta') {
              if (agentMsgId === null) {
                const id = 'a' + Date.now()
                agentMsgId = id
                setThreads((s) => ({ ...s, [k]: [...(s[k] || []), { id, role: 'agent', text: ev.text, at: nowTime() }] }))
              } else {
                const id = agentMsgId
                setThreads((s) => ({ ...s, [k]: (s[k] || []).map((m) => m.id === id ? { ...m, text: m.text + ev.text } : m) }))
              }
            } else if (ev.type === 'done') {
              setRunning(false)
              break outer
            } else if (ev.type === 'error') {
              if (agentMsgId === null) {
                const id = 'a' + Date.now()
                agentMsgId = id
                setThreads((s) => ({ ...s, [k]: [...(s[k] || []), { id, role: 'agent', text: ev.text, at: nowTime() }] }))
              } else {
                const id = agentMsgId
                setThreads((s) => ({ ...s, [k]: (s[k] || []).map((m) => m.id === id ? { ...m, text: m.text + ev.text } : m) }))
              }
              setRunning(false)
              break outer
            }
          }
        }
      } catch (err) {
        if ((err as { name?: string }).name !== 'AbortError') {
          if (agentMsgId === null) {
            const id = 'a' + Date.now()
            agentMsgId = id
            setThreads((s) => ({ ...s, [k]: [...(s[k] || []), { id, role: 'agent', text: 'Error: could not reach server.', at: nowTime() }] }))
          } else {
            const id = agentMsgId
            setThreads((s) => ({ ...s, [k]: (s[k] || []).map((m) => m.id === id ? { ...m, text: m.text + '\nError: could not reach server.' } : m) }))
          }
        }
      } finally {
        setRunning(false)
        abortRef.current = null
      }
      return
    }
    setThreads((s) => ({ ...s, [k]: [...(s[k] || []), { id: 'u' + Date.now(), role: 'user', text: t, at }] }))
    setDraft('')
    setRunning(true)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      const reply = cannedReply(k)
      setThreads((s) => ({ ...s, [k]: [...(s[k] || []), { id: 'a' + Date.now(), role: 'agent', text: reply, at: nowTime() }] }))
      setRunning(false)
    }, 1500)
  }

  function stop() {
    abortRef.current?.abort()
    fetch('/api/chat/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: sessionId }) }).catch(() => {})
    if (timerRef.current) clearTimeout(timerRef.current)
    setRunning(false)
  }

  const live = running
    ? { label: 'Running', color: '#f6b73c', bg: 'rgba(246,183,60,0.1)', border: 'rgba(246,183,60,0.26)' }
    : { label: 'Live', color: '#4ade80', bg: 'rgba(74,222,128,0.1)', border: 'rgba(74,222,128,0.26)' }

  const avBg = `color-mix(in oklab, ${agent.color} 16%, transparent)`
  const avBorder = `color-mix(in oklab, ${agent.color} 42%, transparent)`

  return (
    <section style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0, position: 'relative', animation: 'hpanelin 0.4s var(--ease-out)' }}>
      {/* Header */}
      <div
        style={{
          flex: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '13px 22px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          position: 'relative',
          zIndex: 20,
        }}
      >
        {/* Agent switcher */}
        <div style={{ position: 'relative', minWidth: 0 }}>
          <button
            onClick={() => setAgentMenu((v) => !v)}
            title="Switch agent"
            style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0, background: 'none', border: 'none', padding: '4px 8px 4px 4px', margin: -4, borderRadius: 12, cursor: 'pointer', fontFamily: 'inherit' }}
          >
            <span style={{ width: 34, height: 34, flex: 'none', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, background: avBg, border: `1px solid ${avBorder}`, color: agent.color }}>
              {agent.icon}
            </span>
            <span style={{ minWidth: 0, textAlign: 'left' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 15, color: '#f0f2f8' }}>{agent.name}</span>
                <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="#9298ab" strokeWidth={2}>
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </span>
              <span style={{ display: 'block', fontSize: 11, color: '#6a7088' }}>{(agent.role || 'Agent') + ' · ' + (agent.platform || 'Channel')}</span>
            </span>
          </button>
          {agentMenu && (
            <>
              <div onClick={() => setAgentMenu(false)} style={{ position: 'fixed', inset: 0, zIndex: 30 }} />
              <div
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 'calc(100% + 8px)',
                  width: 264,
                  background: '#0c1119',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: 14,
                  overflow: 'hidden',
                  boxShadow: '0 16px 44px rgba(0,0,0,0.6)',
                  zIndex: 40,
                  animation: 'hcmdin 0.17s cubic-bezier(0.16,1,0.3,1)',
                }}
              >
                <div style={{ padding: '9px 13px 5px', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.09em', color: '#565d72' }}>Message agent</div>
                <div style={{ padding: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {CHAT_AGENTS.map((a: ChatAgent) => {
                    const on = a.key === activeAgent
                    const st = a.running ? 'run' : a.status
                    const dot = st === 'run' ? accent : st === 'online' ? '#4ade80' : '#565d72'
                    const dotGlow = st === 'idle' ? 'none' : `0 0 7px ${st === 'run' ? accent : '#4ade80'}`
                    return (
                      <div
                        key={a.key}
                        onClick={() => selectAgent(a.key)}
                        style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '8px 10px', borderRadius: 10, cursor: 'pointer', background: on ? `color-mix(in oklab, ${accent} 12%, transparent)` : 'transparent' }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = on ? `color-mix(in oklab, ${accent} 12%, transparent)` : 'transparent')}
                      >
                        <span style={{ width: 30, height: 30, flex: 'none', borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, background: `color-mix(in oklab, ${a.color} 16%, transparent)`, border: `1px solid color-mix(in oklab, ${a.color} 42%, transparent)`, color: a.color }}>
                          {a.icon}
                        </span>
                        <span style={{ flex: 1, minWidth: 0 }}>
                          <span style={{ display: 'block', fontSize: 13, fontWeight: 600, color: '#e4e6ee' }}>{a.name}</span>
                          <span style={{ display: 'block', fontSize: 11, color: '#6a7088' }}>{a.role}</span>
                        </span>
                        <span style={{ width: 7, height: 7, flex: 'none', borderRadius: '50%', background: dot, boxShadow: dotGlow }} />
                      </div>
                    )
                  })}
                </div>
              </div>
            </>
          )}
        </div>

        {/* Right cluster: live pill + history + reset */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11, fontWeight: 600, color: live.color, background: live.bg, border: `1px solid ${live.border}`, borderRadius: 99, padding: '4px 11px' }}>
            <span style={{ width: 7, height: 7, borderRadius: '50%', background: live.color, boxShadow: `0 0 7px ${live.color}` }} />
            {live.label}
          </span>
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setHistOpen((v) => !v)}
              title="Past sessions"
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: '#161b27', color: '#9298ab', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '6px 11px', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer' }}
            >
              <svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 3v5h5" />
                <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
                <path d="M12 7v5l4 2" />
              </svg>
              History
              {pastList.length > 0 && <span className="mono" style={{ fontSize: 10, color: '#6a7088' }}>{pastList.length}</span>}
            </button>
            {histOpen && (
              <>
                <div onClick={() => setHistOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 20 }} />
                <div style={{ position: 'absolute', right: 0, top: 'calc(100% + 7px)', width: 264, background: '#0c1119', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 12, overflow: 'hidden', boxShadow: '0 16px 44px rgba(0,0,0,0.6)', zIndex: 30, animation: 'hcmdin 0.16s cubic-bezier(0.16,1,0.3,1)' }}>
                  <div style={{ padding: '10px 13px 6px', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.09em', color: '#565d72' }}>Past sessions</div>
                  <div style={{ padding: 5, display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 300, overflowY: 'auto' }}>
                    {pastList.length === 0 ? (
                      <div style={{ padding: '10px 11px', fontSize: 12, color: '#565d72' }}>No past sessions yet.</div>
                    ) : (
                      pastList.map((p) => (
                        <div
                          key={p.id}
                          onClick={() => { setViewSession(p); setHistOpen(false) }}
                          style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '9px 11px', borderRadius: 9, cursor: 'pointer' }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
                          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                        >
                          <span style={{ fontSize: 12.5, fontWeight: 500, color: '#e4e6ee' }}>{p.title}</span>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 10.5, color: '#6a7088' }}>
                            {p.when} <span style={{ color: '#3c4254' }}>·</span> {p.msgs.length} messages
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
          <button
            onClick={() => setThreads((s) => ({ ...s, [activeAgent]: [] }))}
            title="Reset conversation"
            style={{ background: '#161b27', color: '#9298ab', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '6px 12px', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer' }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = '#fb6f6f'; e.currentTarget.style.color = '#fb6f6f' }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = '#9298ab' }}
          >
            Reset
          </button>
        </div>
      </div>

      {/* Viewing-past banner */}
      {viewSession && (
        <div style={{ flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '9px 22px', background: 'color-mix(in oklab, var(--ac) 8%, transparent)', borderBottom: '1px solid rgba(255,255,255,0.06)', position: 'relative', zIndex: 1 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#c6cad8' }}>
            <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="var(--ac)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 3v5h5" />
              <path d="M3.05 13A9 9 0 1 0 6 5.3L3 8" />
              <path d="M12 7v5l4 2" />
            </svg>
            Viewing past session · <span style={{ color: '#9aa0b4' }}>{viewSession.title} · {viewSession.when}</span>
          </span>
          <button onClick={() => setViewSession(null)} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'transparent', color: 'var(--ac)', border: 'none', fontSize: 12, fontFamily: 'inherit', cursor: 'pointer', padding: 0 }}>
            Return to current
            <svg width={13} height={13} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      )}

      {/* Message list */}
      <div ref={listRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', padding: '22px 26px', display: 'flex', flexDirection: 'column', gap: 4, position: 'relative', zIndex: 1 }}>
        {displayThread.length === 0 && !running ? (
          <div style={{ margin: 'auto', textAlign: 'center', padding: '40px 20px' }}>
            <div style={{ fontSize: 44, lineHeight: 1, marginBottom: 14, color: agent.color }}>{agent.icon}</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: '#e4e6ee', marginBottom: 6 }}>Chat with {agent.name}</div>
            <div style={{ fontSize: 13, color: '#6a7088', maxWidth: 320, margin: '0 auto' }}>{agent.role} — send a message to start a conversation.</div>
          </div>
        ) : (
          displayThread.map((m, i) => {
            const showDivider = i === 0 && !viewSession
            return (
              <div key={m.id}>
                {showDivider && (
                  <div style={{ position: 'relative', textAlign: 'center', margin: '6px 0 12px' }}>
                    <div style={{ position: 'absolute', left: 0, right: 0, top: '50%', height: 1, background: 'rgba(255,255,255,0.06)' }} />
                    <span style={{ position: 'relative', background: '#080b11', padding: '0 12px', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#565d72' }}>Today</span>
                  </div>
                )}
                {m.role === 'plan' ? (
                  <PlanBlock
                    msgId={m.id}
                    accent={accent}
                    mainOpen={planMainOpen[m.id] !== false}
                    stepOpen={planStepOpen}
                    onToggleMain={() => setPlanMainOpen((s) => ({ ...s, [m.id]: s[m.id] === false }))}
                    onToggleStep={(key) => setPlanStepOpen((s) => ({ ...s, [key]: !(s[key] ?? key.endsWith('/3')) }))}
                  />
                ) : (
                  <div style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start', margin: '3px 0' }}>
                    <div
                      style={{
                        maxWidth: '74%',
                        padding: '10px 15px',
                        borderRadius: 16,
                        borderBottomRightRadius: m.role === 'user' ? 5 : 16,
                        borderBottomLeftRadius: m.role === 'user' ? 16 : 5,
                        background: m.role === 'user' ? `linear-gradient(135deg, color-mix(in oklab, ${accent} 76%, #c2410c), ${accent})` : '#11151f',
                        border: m.role === 'user' ? 'none' : '1px solid rgba(255,255,255,0.08)',
                        color: m.role === 'user' ? '#1c1404' : '#d8dbe6',
                        boxShadow: '0 2px 12px rgba(0,0,0,0.25)',
                      }}
                    >
                      <div style={{ fontSize: 14, lineHeight: 1.55, wordWrap: 'break-word' }}>
                        <MessageContent text={m.text} />
                      </div>
                      <div
                        title={`${todayStr} ${m.at}`}
                        style={{ fontSize: 9.5, marginTop: 5, textAlign: 'right', color: m.role === 'user' ? 'rgba(28,20,4,0.6)' : '#565d72', cursor: 'default' }}
                      >
                        {m.at}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )
          })
        )}
        {running && !viewSession && (
          <div style={{ display: 'flex', justifyContent: 'flex-start', margin: '3px 0' }}>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: '#11151f', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 16, borderBottomLeftRadius: 5, padding: '14px 16px' }}>
              {[0, 0.18, 0.36].map((d) => (
                <span key={d} style={{ width: 7, height: 7, borderRadius: '50%', background: '#9aa0b4', animation: `hbounce 1.3s ease-in-out ${d}s infinite` }} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Composer */}
      <div style={{ flex: 'none', padding: '14px 22px 18px', position: 'relative', zIndex: 1 }}>
        {/* Slash command dropdown — floats above composer */}
        {cmdOpen && filteredCmds.length > 0 && (
          <div
            style={{
              position: 'absolute', bottom: 'calc(100% - 14px)', left: 22, right: 22, marginBottom: 4,
              background: '#0c1119', border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 12, overflow: 'hidden', zIndex: 50,
              boxShadow: '0 -8px 32px rgba(0,0,0,0.5)',
              animation: 'hcmdin 0.15s cubic-bezier(0.16,1,0.3,1)',
            }}
          >
            <div style={{ padding: '7px 13px 4px', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.09em', color: '#565d72' }}>Commands</div>
            {filteredCmds.map((c, i) => (
              <div
                key={c.cmd}
                onMouseDown={(e) => { e.preventDefault(); setDraft(c.cmd + ' '); setCmdOpen(false) }}
                onMouseEnter={() => setCmdIdx(i)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12, padding: '8px 13px', cursor: 'pointer',
                  background: i === cmdIdx ? 'rgba(255,255,255,0.07)' : 'transparent',
                }}
              >
                <span className="mono" style={{ fontSize: 12.5, color: 'var(--ac)', flex: 'none' }}>{c.cmd}</span>
                <span style={{ fontSize: 11.5, color: '#6a7088' }}>{c.description}</span>
              </div>
            ))}
          </div>
        )}

        <div
          style={{ background: '#11151f', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16, padding: '14px 16px 11px', display: 'flex', flexDirection: 'column', gap: 11 }}
          onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--ac)')}
          onBlur={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')}
        >
          <textarea
            value={draft}
            onChange={(e) => {
              const v = e.target.value
              setDraft(v)
              if (v.startsWith('/') && !v.includes(' ')) {
                setCmdOpen(true)
                setCmdIdx(0)
              } else {
                setCmdOpen(false)
              }
            }}
            onKeyDown={(e) => {
              if (cmdOpen && filteredCmds.length > 0) {
                if (e.key === 'ArrowUp') {
                  e.preventDefault()
                  setCmdIdx((i) => (i - 1 + filteredCmds.length) % filteredCmds.length)
                  return
                }
                if (e.key === 'ArrowDown') {
                  e.preventDefault()
                  setCmdIdx((i) => (i + 1) % filteredCmds.length)
                  return
                }
                if (e.key === 'Enter' || e.key === 'Tab') {
                  e.preventDefault()
                  setDraft(filteredCmds[cmdIdx].cmd + ' ')
                  setCmdOpen(false)
                  return
                }
                if (e.key === 'Escape') {
                  e.preventDefault()
                  setCmdOpen(false)
                  return
                }
              }
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
            rows={1}
            placeholder={`Message ${agent.name}…`}
            style={{ width: '100%', resize: 'none', minHeight: 26, maxHeight: 140, background: 'none', border: 'none', color: '#e9ebf2', fontFamily: 'inherit', fontSize: 14, lineHeight: 1.5, outline: 'none' }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
              {/* Static action buttons */}
              {[
                { t: 'Attach', d: 'M21 8v8a5 5 0 0 1-10 0V6a3 3 0 0 1 6 0v9a1 1 0 0 1-2 0V7', s: 17 },
                { t: 'Save', d: 'M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z', s: 16 },
              ].map((b) => (
                <button key={b.t} title={b.t} style={{ width: 30, height: 30, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'none', border: 'none', borderRadius: 8, color: '#6a7088', cursor: 'pointer' }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#e9ebf2'; e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = '#6a7088'; e.currentTarget.style.background = 'none' }}>
                  <svg width={b.s} height={b.s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d={b.d} /></svg>
                </button>
              ))}

              {/* Voice button — hidden when SpeechRecognition is unavailable */}
              {hasSpeech && (
                <button
                  title={listening ? 'Stop recording' : 'Voice input'}
                  onClick={toggleVoice}
                  style={{
                    width: 30, height: 30, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    background: listening ? 'rgba(251,111,111,0.12)' : 'none',
                    border: listening ? '1px solid rgba(251,111,111,0.3)' : 'none',
                    borderRadius: 8,
                    color: listening ? '#fb6f6f' : '#6a7088',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => {
                    if (!listening) { e.currentTarget.style.color = '#e9ebf2'; e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }
                  }}
                  onMouseLeave={(e) => {
                    if (!listening) { e.currentTarget.style.color = '#6a7088'; e.currentTarget.style.background = 'none' }
                  }}
                >
                  <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                    <rect x={9} y={3} width={6} height={11} rx={3} />
                    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
                  </svg>
                </button>
              )}

              <span style={{ width: 1, height: 18, background: 'rgba(255,255,255,0.1)', margin: '0 2px' }} />

              {/* Single click-away backdrop closes any open composer dropdown */}
              {composerMenu !== null && <div onClick={() => setComposerMenu(null)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />}

              <ComposerDropdown
                menuKey="profile" value={profile} options={profileOpts} open={composerMenu === 'profile'} variant="accent" minWidth={168}
                onToggle={() => setComposerMenu((m) => (m === 'profile' ? null : 'profile'))}
                onPick={(v) => { setProfile(v); setComposerMenu(null) }}
                icon={<svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><circle cx={12} cy={8} r={4} /><path d="M4 21a8 8 0 0 1 16 0" /></svg>}
              />
              <ComposerDropdown
                menuKey="folder" value={folder} options={FOLDER_OPTIONS} open={composerMenu === 'folder'} variant="pill" minWidth={168}
                onToggle={() => setComposerMenu((m) => (m === 'folder' ? null : 'folder'))}
                onPick={(v) => { setFolder(v); setComposerMenu(null) }}
                icon={<svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="#9298ab" strokeWidth={2}><path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>}
              />
              <ComposerDropdown
                menuKey="model" value={model} options={modelOpts} open={composerMenu === 'model'} variant="pill" minWidth={190}
                onToggle={() => setComposerMenu((m) => (m === 'model' ? null : 'model'))}
                onPick={(v) => { setModel(v); setComposerMenu(null) }}
                icon={<svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="#9298ab" strokeWidth={2}><circle cx={12} cy={12} r={3} /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>}
              />
              <ComposerDropdown
                menuKey="reasoning" value={reason} options={REASON_OPTIONS} open={composerMenu === 'reasoning'} variant="pill" minWidth={160}
                onToggle={() => setComposerMenu((m) => (m === 'reasoning' ? null : 'reasoning'))}
                onPick={(v) => { setReason(v); setComposerMenu(null) }}
                icon={<svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="#9298ab" strokeWidth={2}><circle cx={12} cy={12} r={9} /><path d="M12 3v18" /></svg>}
              />
            </div>

            {/* Right cluster: context ring + send/stop */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 'none' }}>
              <span style={{ position: 'relative', width: 30, height: 30, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }} title="Context usage">
                <svg width={30} height={30} viewBox="0 0 24 24" style={{ position: 'absolute', inset: 0 }}>
                  <circle cx={12} cy={12} r={9} fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth={2.4} />
                  <circle cx={12} cy={12} r={9} fill="none" stroke="var(--ac)" strokeWidth={2.4} strokeLinecap="round" strokeDasharray={ringDash} transform="rotate(-90 12 12)" />
                </svg>
                <span className="mono" style={{ fontSize: 9, color: '#9298ab' }}>{ctxNum}</span>
              </span>
              {running ? (
                <button onClick={stop} title="Stop" style={{ width: 38, height: 38, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: '#f4434f', color: '#fff', border: 'none', borderRadius: '50%', cursor: 'pointer' }}>
                  <svg width={14} height={14} viewBox="0 0 24 24" fill="#fff"><rect x={6} y={6} width={12} height={12} rx={2} /></svg>
                </button>
              ) : (
                <button onClick={() => void send()} title="Send" style={{ width: 38, height: 38, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'var(--ac)', color: '#1c1404', border: 'none', borderRadius: '50%', cursor: 'pointer' }}>
                  <svg width={15} height={15} viewBox="0 0 24 24" fill="#1c1404"><path d="M3 11l18-8-8 18-2-7z" /></svg>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// ── Chat panel ───────────────────────────────────────────────────────────────