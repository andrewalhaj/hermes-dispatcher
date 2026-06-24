import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  INITIAL_THREADS,
  MODEL_OPTIONS,
  PAST_SESSIONS,
  PROFILE_OPTIONS,
  REASON_OPTIONS,
  cannedReply,
  epochToWhen,
  nowTime,
} from '../../data/chat'
import type { Message, PastSession } from '../../data/types'
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

// ── Media image with onError fallback ───────────────────────────────────────

function MediaImage({ src, alt }: { src: string; alt: string }) {
  const [failed, setFailed] = useState(false)
  if (failed) return <span style={{ fontSize: 13, color: '#9298ab' }}>{alt}</span>
  return (
    <img
      src={src}
      alt={alt}
      style={{ maxWidth: '100%', borderRadius: 10, marginTop: 8, display: 'block' }}
      onError={() => setFailed(true)}
    />
  )
}

// ── Inline markdown parser ───────────────────────────────────────────────────
// Order matters: backtick code first, then ** bold, then * or _ italic, then ~~, then links.

function parseInline(text: string, accent: string, prefix: string): ReactNode[] {
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(_[^_]+_)|(~~[^~]+~~)|(\[([^\]]+)\]\(([^)]+)\))/g
  const nodes: ReactNode[] = []
  let last = 0
  let ki = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const key = `${prefix}-k${ki++}`
    if (m[1]) {
      // `inline code`
      nodes.push(
        <code key={key} style={{ fontFamily: 'IBM Plex Mono, monospace', fontSize: '0.88em', padding: '1px 5px', background: 'rgba(255,255,255,0.08)', borderRadius: 4 }}>
          {m[1].slice(1, -1)}
        </code>
      )
    } else if (m[2]) {
      // **bold**
      nodes.push(<strong key={key}>{m[2].slice(2, -2)}</strong>)
    } else if (m[3]) {
      // *italic*
      nodes.push(<em key={key}>{m[3].slice(1, -1)}</em>)
    } else if (m[4]) {
      // _italic_
      nodes.push(<em key={key}>{m[4].slice(1, -1)}</em>)
    } else if (m[5]) {
      // ~~strikethrough~~
      nodes.push(<del key={key}>{m[5].slice(2, -2)}</del>)
    } else if (m[6]) {
      // [link text](url)
      nodes.push(
        <a key={key} href={m[8]} target="_blank" rel="noopener noreferrer" style={{ color: accent || '#6aa6ff', textDecoration: 'underline' }}>
          {m[7]}
        </a>
      )
    }
    last = m.index + m[0].length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

// ── Media block helpers ──────────────────────────────────────────────────────

const _IMG_EXT = /\.(jpg|jpeg|png|gif|webp)$/i
const _VID_EXT = /\.(mp4|webm)$/i
const _AUD_EXT = /\.(mp3|ogg|wav)$/i

function renderMedia(path: string, key: string): ReactNode {
  const url = `/api/media?path=${encodeURIComponent(path)}`
  const fname = path.split('/').pop() || path
  if (_IMG_EXT.test(path)) return <MediaImage key={key} src={url} alt={fname} />
  if (_VID_EXT.test(path)) return <video key={key} controls style={{ maxWidth: '100%', borderRadius: 10, marginTop: 8, display: 'block' }} src={url} />
  if (_AUD_EXT.test(path)) return <audio key={key} controls style={{ width: '100%', marginTop: 8 }} src={url} />
  return <a key={key} href={url} target="_blank" rel="noopener noreferrer">{fname}</a>
}

function renderMarkdownImage(alt: string, rawUrl: string, key: string): ReactNode {
  const src = (rawUrl.startsWith('/') || rawUrl.startsWith('http://localhost'))
    ? `/api/media?path=${encodeURIComponent(rawUrl)}`
    : rawUrl
  return <MediaImage key={key} src={src} alt={alt || rawUrl} />
}

// ── Block + inline text renderer ─────────────────────────────────────────────

function renderTextSegment(content: string, accent: string, segIdx: number): ReactNode {
  const lines = content.split('\n')
  const nodes: ReactNode[] = []
  lines.forEach((line, li) => {
    const key = `${segIdx}-${li}`
    const tr = line.trim()
    // MEDIA: token
    const med = /^MEDIA:(\S+)/.exec(tr)
    if (med) { nodes.push(renderMedia(med[1], key)); return }
    // Standalone markdown image (whole line)
    const img = /^!\[([^\]]*)\]\(([^)]+)\)$/.exec(tr)
    if (img) { nodes.push(renderMarkdownImage(img[1], img[2], key)); return }
    // Horizontal rule
    if (tr === '---') {
      nodes.push(<hr key={key} style={{ border: 'none', borderTop: '1px solid rgba(255,255,255,0.08)', margin: '10px 0' }} />)
      return
    }
    // Headings — check ### before ## before # to avoid prefix conflicts
    let hm: RegExpExecArray | null
    if ((hm = /^### (.+)/.exec(line)) !== null) {
      nodes.push(<div key={key} style={{ fontWeight: 700, fontSize: 15.5, lineHeight: 1.4, margin: '5px 0 2px' }}>{parseInline(hm[1], accent, key)}</div>)
      return
    }
    if ((hm = /^## (.+)/.exec(line)) !== null) {
      nodes.push(<div key={key} style={{ fontWeight: 700, fontSize: 17, lineHeight: 1.4, margin: '6px 0 3px' }}>{parseInline(hm[1], accent, key)}</div>)
      return
    }
    if ((hm = /^# (.+)/.exec(line)) !== null) {
      nodes.push(<div key={key} style={{ fontWeight: 700, fontSize: 19, lineHeight: 1.4, margin: '8px 0 4px' }}>{parseInline(hm[1], accent, key)}</div>)
      return
    }
    // Normal text line — skip empty trailing line
    const isLast = li === lines.length - 1
    if (isLast && tr === '') return
    nodes.push(
      <span key={key}>
        {parseInline(line, accent, key)}
        {!isLast && <br />}
      </span>
    )
  })
  return <>{nodes}</>
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

function MessageContent({ text, accent }: { text: string; accent: string }) {
  const segs = parseMessageText(text)
  return (
    <>
      {segs.map((seg, i) => {
        if (seg.type === 'mermaid') return <MermaidBlock key={i} content={seg.content} />
        if (seg.type === 'code') return <CodeBlock key={i} lang={seg.lang} content={seg.content} />
        return (
          <div key={i} style={{ fontSize: 15, lineHeight: 1.62, wordBreak: 'break-word' }}>
            {renderTextSegment(seg.content, accent, i)}
          </div>
        )
      })}
    </>
  )
}

interface ChatProps {
  accent: string
  isActive?: boolean
  onUnreadChange?: (total: number) => void
}

// ── Read/delivered tick (echoes reference CheckCheck / Check) ─────────────────

function StatusTick({ color }: { color: string }) {
  // Double-check "read" style tick, mirrors the reference's CheckCheck affordance.
  return (
    <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none' }}>
      <path d="M1 13l4 4L13 7" />
      <path d="M11 13l4 4L23 7" />
    </svg>
  )
}

// ── Inline icons (lucide-react translated to our inline-SVG convention) ───────

function SmilePlusIcon({ size = 16, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none' }}>
      <path d="M22 11v1a10 10 0 1 1-9-10" />
      <path d="M8 14s1.5 2 4 2 4-2 4-2" />
      <line x1={9} y1={9} x2={9.01} y2={9} />
      <line x1={15} y1={9} x2={15.01} y2={9} />
      <path d="M16 5h6M19 2v6" />
    </svg>
  )
}

function SearchIcon({ size = 18, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none' }}>
      <circle cx={11} cy={11} r={8} />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  )
}

// ── Search types + helpers ───────────────────────────────────────────────────

interface SessionHit { session_id: string; session_title: string; snippet: string; message_role: string; timestamp: string }
interface ReferenceHit { file: string; path: string; snippet: string; line: number }
interface SkillHit { name: string; path: string; snippet: string }
interface SearchResults { query: string; sessions: SessionHit[]; references: ReferenceHit[]; skills: SkillHit[] }

const EMPTY_RESULTS: SearchResults = { query: '', sessions: [], references: [], skills: [] }

/** Render a snippet where the backend wrapped matched terms in **double-asterisks**, bolding them in gold. */
function renderSnippet(snippet: string, accent: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const re = /\*\*([^*]+)\*\*/g
  let last = 0
  let ki = 0
  let m: RegExpExecArray | null
  while ((m = re.exec(snippet)) !== null) {
    if (m.index > last) nodes.push(snippet.slice(last, m.index))
    nodes.push(<strong key={`hl${ki++}`} style={{ color: accent, fontWeight: 700 }}>{m[1]}</strong>)
    last = m.index + m[0].length
  }
  if (last < snippet.length) nodes.push(snippet.slice(last))
  return nodes
}

/** ISO timestamp → relative "when" string (mirrors epochToWhen for ISO input). */
function isoToWhen(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000)
  const timeStr = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  if (diffDays === 0) return `Today · ${timeStr}`
  if (diffDays === 1) return `Yesterday · ${timeStr}`
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' · ' + timeStr
}

// Quick-reaction palette for the SmilePlus picker.
const REACTION_EMOJIS = ['👍', '🙌', '✨', '🎉', '❤️', '👀']

type Reaction = { emoji: string; count: number; reacted: boolean }

interface Attachment {
  path: string
  filename: string
  mime: string
  is_image: boolean
  is_text: boolean
  text_content?: string
  preview_url?: string // object URL for image preview in UI
}

// ── Live data types (sidebar) ────────────────────────────────────────────────

interface LiveAgent {
  name: string
  role: string
  model: string
  avatar: string
  color: string
  status: 'busy' | 'online' | 'idle'
  today?: number
  completed?: number
  total?: number
  success?: number
  lastActive?: string
}

interface CronJob {
  id: string
  name: string
  schedule: string
  enabled: boolean
  lastStatus?: string
  lastRunAt?: string
}

// One run's output in the combined cron feed (/api/cron/output).
interface CronOutputMsg {
  role: string
  content: string
  created_at: number
  job_id: string
  file?: string
}

// Clock icon for cron channels (inline SVG, our convention).
function ClockIcon({ size = 15, color = 'currentColor' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" style={{ flex: 'none' }}>
      <circle cx={12} cy={12} r={9} />
      <path d="M12 7v5l3 2" />
    </svg>
  )
}

const clone = <T,>(o: T): T => JSON.parse(JSON.stringify(o)) as T

// ── Left sidebar: Hermes / Channels / Agents (+ collapsible Swarm) ───────────

function statusDot(status: string): { color: string; glow: string } {
  if (status === 'busy') return { color: '#f6b73c', glow: '0 0 8px #f6b73c' }
  if (status === 'online') return { color: '#4ade80', glow: '0 0 8px #4ade80' }
  return { color: '#565d72', glow: 'none' }
}

interface AvatarProps { letter: string; color: string; size: number; dot?: string; dotGlow?: string }
function Avatar({ letter, color, size, dot, dotGlow }: AvatarProps) {
  return (
    <span style={{ position: 'relative', width: size, height: size, flex: 'none' }}>
      <span style={{
        width: size, height: size, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: size * 0.5, fontWeight: 700, fontFamily: 'var(--font-display)',
        background: `color-mix(in oklab, ${color} 16%, transparent)`,
        border: `1px solid color-mix(in oklab, ${color} 42%, transparent)`,
        color,
      }}>{letter}</span>
      {dot && <span style={{ position: 'absolute', bottom: 0, right: 0, width: 10, height: 10, borderRadius: '50%', background: dot, boxShadow: dotGlow || 'none', border: '2px solid #080b11' }} />}
    </span>
  )
}

interface ChatSidebarProps {
  accent: string
  liveAgents: LiveAgent[]
  cronJobs: CronJob[]
  activeAgent: string
  activeCron: string | null
  swarmOpen: boolean
  unreadCounts: Record<string, number>
  searchMode: boolean
  onToggleSwarm: () => void
  onSelectAgent: (key: string) => void
  onSelectCron: () => void
  onToggleSearch: () => void
}

function GroupHeader({ label }: { label: string }) {
  return (
    <div style={{ padding: '14px 14px 6px', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#565d72' }}>
      {label}
    </div>
  )
}

function ChatSidebar({ accent, liveAgents, cronJobs, activeAgent, activeCron, swarmOpen, unreadCounts, searchMode, onToggleSwarm, onSelectAgent, onSelectCron, onToggleSearch }: ChatSidebarProps) {
  const hermes = liveAgents.find((a) => a.name === 'default')
  const others = liveAgents.filter((a) => a.name !== 'default')
  const nonSwarm = others.filter((a) => !a.name.startsWith('swarm-'))
  const swarm = others.filter((a) => a.name.startsWith('swarm-'))

  // A selectable agent row — Telegram-style (large avatar, name + preview, timestamp, badge).
  const agentRow = (a: LiveAgent, label?: string) => {
    const selected = !activeCron && activeAgent === a.name
    const d = statusDot(a.status)
    const now = new Date()
    const timeStr = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    return (
      <div
        key={a.name}
        onClick={() => onSelectAgent(a.name)}
        style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '10px 12px 10px 13px', cursor: 'pointer',
          background: selected ? 'rgba(246,183,60,0.12)' : 'transparent',
          transition: 'background 0.14s',
        }}
        onMouseEnter={(e) => { if (!selected) e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
        onMouseLeave={(e) => { if (!selected) e.currentTarget.style.background = selected ? 'rgba(246,183,60,0.12)' : 'transparent' }}
      >
        {/* Avatar — 44px circle */}
        <Avatar letter={a.avatar} color={a.color} size={44} dot={d.color} dotGlow={d.glow} />

        {/* Middle: name + subtitle */}
        <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
          <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: selected ? '#f7e9c6' : '#e4e6ee', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
              {label ?? a.name}
            </span>
            {/* Timestamp top-right */}
            <span style={{ fontSize: 11, color: '#565d72', flex: 'none' }}>{timeStr}</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
            <span style={{ fontSize: 12, color: '#9298ab', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
              {a.role}
            </span>
            {/* Unread badge bottom-right */}
            {(unreadCounts[a.name] || 0) > 0 && (
              <span style={{
                minWidth: 20, height: 20, borderRadius: 10,
                background: '#3b82f6', color: '#fff',
                fontSize: 11, fontWeight: 700,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '0 5px', flexShrink: 0,
              }}>
                {unreadCounts[a.name]}
              </span>
            )}
          </span>
        </span>
      </div>
    )
  }

  return (
    <aside
      style={{
        flex: 'none', width: 252, display: 'flex', flexDirection: 'column', minHeight: 0,
        borderRight: '1px solid var(--tile-border)', background: 'var(--s3)',
        overflowY: 'auto', overflowX: 'hidden',
      }}
    >
      {/* Search button pinned to top of sidebar */}
      <div style={{ flex: 'none', padding: '12px 12px 4px', display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={onToggleSearch}
          title={searchMode ? 'Close search' : 'Search messages, references, and skills'}
          style={{
            width: 28, height: 28, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            background: searchMode ? 'color-mix(in oklab, var(--ac) 14%, transparent)' : 'transparent',
            border: `1px solid ${searchMode ? 'color-mix(in oklab, var(--ac) 38%, transparent)' : 'rgba(255,255,255,0.08)'}`,
            borderRadius: 7, cursor: 'pointer', color: searchMode ? 'var(--ac)' : '#565d72', transition: 'all 0.16s',
          }}
          onMouseEnter={(e) => { if (!searchMode) { e.currentTarget.style.color = '#e9ebf2'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.18)' } }}
          onMouseLeave={(e) => { if (!searchMode) { e.currentTarget.style.color = '#565d72'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.08)' } }}
        >
          <SearchIcon size={13} />
        </button>
      </div>
      {/* HERMES */}
      <GroupHeader label="Hermes" />
      {hermes
        ? agentRow(hermes, 'Hermes')
        : agentRow({ name: 'default', role: 'Coordinator', model: '', avatar: 'H', color: accent, status: 'online' }, 'Hermes')}

      {/* CHANNELS — single aggregated "Cron Jobs" entry (Telegram-style row) */}
      <GroupHeader label="Channels" />
      {(() => {
        const selected = activeCron === 'cron'
        const now = new Date()
        const timeStr = now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
        return (
          <div
            onClick={onSelectCron}
            title="Combined output feed from all scheduled cron jobs"
            style={{
              display: 'flex', alignItems: 'center', gap: 12,
              padding: '10px 12px 10px 13px', cursor: 'pointer',
              background: selected ? 'rgba(246,183,60,0.12)' : 'transparent',
              transition: 'background 0.14s',
            }}
            onMouseEnter={(e) => { if (!selected) e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
            onMouseLeave={(e) => { if (!selected) e.currentTarget.style.background = selected ? 'rgba(246,183,60,0.12)' : 'transparent' }}
          >
            {/* Clock-icon avatar — 44px */}
            <span style={{ position: 'relative', width: 44, height: 44, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', background: 'color-mix(in oklab, #9b8cff 16%, transparent)', border: '1px solid color-mix(in oklab, #9b8cff 42%, transparent)', color: '#9b8cff' }}>
              <ClockIcon size={22} color="#9b8cff" />
            </span>
            {/* Middle: name + subtitle */}
            <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 2 }}>
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: selected ? '#f7e9c6' : '#e4e6ee', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>Cron Jobs</span>
                <span style={{ fontSize: 11, color: '#565d72', flex: 'none' }}>{timeStr}</span>
              </span>
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                <span style={{ fontSize: 12, color: '#9298ab', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>{cronJobs.length} scheduled</span>
                {(unreadCounts['cron'] || 0) > 0 && (
                  <span style={{
                    minWidth: 20, height: 20, borderRadius: 10,
                    background: '#3b82f6', color: '#fff',
                    fontSize: 11, fontWeight: 700,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    padding: '0 5px', flexShrink: 0,
                  }}>
                    {unreadCounts['cron']}
                  </span>
                )}
              </span>
            </span>
          </div>
        )
      })()}

      {/* AGENTS */}
      <GroupHeader label="Agents" />
      {nonSwarm.length === 0 ? (
        <div style={{ padding: '4px 14px 8px', fontSize: 11.5, color: '#565d72' }}>No agents</div>
      ) : (
        nonSwarm.map((a) => agentRow(a))
      )}

      {/* SWARM (collapsible) */}
      {swarm.length > 0 && (
        <>
          <div
            onClick={onToggleSwarm}
            style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '14px 14px 6px', cursor: 'pointer', userSelect: 'none' }}
          >
            <svg width={11} height={11} viewBox="0 0 24 24" fill="none" stroke="#565d72" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" style={{ transform: swarmOpen ? 'rotate(90deg)' : 'none', transition: 'transform 0.16s' }}>
              <path d="M9 6l6 6-6 6" />
            </svg>
            <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#565d72' }}>Swarm</span>
            <span style={{ fontSize: 10, color: '#454b5e', fontFamily: 'IBM Plex Mono, monospace' }}>{swarm.length}</span>
          </div>
          {swarmOpen && swarm.map((a) => agentRow(a))}
        </>
      )}

      <div style={{ height: 12, flex: 'none' }} />
    </aside>
  )
}

export default function Chat({ accent, isActive, onUnreadChange }: ChatProps) {
  const [activeAgent, setActiveAgent] = useState('default')
  const [threads, setThreads] = useState<Record<string, Message[]>>(() => clone(INITIAL_THREADS))
  const [draft, setDraft] = useState('')
  const [running, setRunning] = useState(false)
  const [viewSession, setViewSession] = useState<PastSession | null>(null)
  const [composerMenu, setComposerMenu] = useState<string | null>(null)
  const [profile] = useState('default')
  const [model, setModel] = useState(() => localStorage.getItem('hermes-chat-model') || 'Claude Sonnet 4.6')
  const [reason, setReason] = useState(() => localStorage.getItem('hermes-chat-reason') || 'xhigh')
  const [planMainOpen, setPlanMainOpen] = useState<Record<string, boolean>>({})
  const [planStepOpen, setPlanStepOpen] = useState<Record<string, boolean>>({})

  // Per-agent/channel unread message counts (badge state).
  const [unreadCounts, setUnreadCounts] = useState<Record<string, number>>({})
  // Accumulated SSE text for the in-flight agent message — available at `done`
  // time for the browser-notification preview (thread state updates are async).
  const lastMsgTextRef = useRef('')

  // ── Sidebar live data ─────────────────────────────────────────────────────
  const [liveAgents, setLiveAgents] = useState<LiveAgent[]>([])
  const [cronJobs, setCronJobs] = useState<CronJob[]>([])
  const [swarmOpen, setSwarmOpen] = useState(false)
  // When a cron channel is selected: 'cron'; else null (agent/Hermes mode).
  const [activeCron, setActiveCron] = useState<string | null>(null)
  const [cronOutput, setCronOutput] = useState<CronOutputMsg[]>([])
  const [cronLoading, setCronLoading] = useState(false)

  // Per-agent Kanban task reports (rendered as a message feed in worker channels).
  const [agentReports, setAgentReports] = useState<Record<string, Message[]>>({})
  const [reportsLoading, setReportsLoading] = useState(false)

  // Per-message emoji reactions (local UX state — not persisted to the backend).
  const [reactions, setReactions] = useState<Record<string, Reaction[]>>({})
  const [reactionPicker, setReactionPicker] = useState<string | null>(null)
  const [composerEmoji, setComposerEmoji] = useState(false)

  // ── File / image attachments (paste + paperclip) ──────────────────────────
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)

  // ── Telegram-style inline search ──────────────────────────────────────────
  const [searchMode, setSearchMode] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SearchResults>(EMPTY_RESULTS)
  const [searchLoading, setSearchLoading] = useState(false)
  const [expandedHit, setExpandedHit] = useState<string | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)
  const searchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const searchAbortRef = useRef<AbortController | null>(null)

  function exitSearch() {
    setSearchMode(false)
    setSearchQuery('')
    setSearchResults(EMPTY_RESULTS)
    setSearchLoading(false)
    setExpandedHit(null)
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)
    searchAbortRef.current?.abort()
  }

  // Debounced live search (300ms, min 2 chars).
  useEffect(() => {
    if (!searchMode) return
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)
    const q = searchQuery.trim()
    if (q.length < 2) {
      setSearchResults(EMPTY_RESULTS)
      setSearchLoading(false)
      searchAbortRef.current?.abort()
      return
    }
    setSearchLoading(true)
    searchDebounceRef.current = setTimeout(() => {
      searchAbortRef.current?.abort()
      const controller = new AbortController()
      searchAbortRef.current = controller
      fetch(`/api/search?q=${encodeURIComponent(q)}`, { signal: controller.signal })
        .then((r) => r.json())
        .then((data: SearchResults) => {
          setSearchResults({
            query: data.query ?? q,
            sessions: data.sessions ?? [],
            references: data.references ?? [],
            skills: data.skills ?? [],
          })
          setSearchLoading(false)
        })
        .catch((err) => {
          if ((err as { name?: string }).name !== 'AbortError') {
            setSearchResults(EMPTY_RESULTS)
            setSearchLoading(false)
          }
        })
    }, 300)
  }, [searchQuery, searchMode])

  // Autofocus the search input when entering search mode.
  useEffect(() => {
    if (searchMode) searchInputRef.current?.focus()
  }, [searchMode])

  // Load a session by id (reuses the same fetch mechanism as initial load).
  async function openSession(sid: string, title?: string) {
    const known = (hermesSessions || []).find((s) => s.id === sid)
    const base: PastSession = known ?? { id: sid, title: title || sid, when: '', msgs: [] }
    setActiveAgent('default')
    setActiveCron(null)
    setCronOutput([])
    try {
      const msgRes = await fetch(`/api/chat/sessions/${sid}/messages`)
      const msgs = await msgRes.json() as Message[]
      setViewSession({ ...base, msgs })
    } catch {
      setViewSession({ ...base, msgs: [] })
    }
    localStorage.setItem('hermes-chat-last-session', sid)
  }

  function handleSearchSessionClick(hit: SessionHit) {
    void openSession(hit.session_id, hit.session_title)
    exitSearch()
  }

  function toggleReaction(msgId: string, emoji: string) {
    setReactions((s) => {
      const list = s[msgId] ? [...s[msgId]] : []
      const idx = list.findIndex((r) => r.emoji === emoji)
      if (idx === -1) {
        list.push({ emoji, count: 1, reacted: true })
      } else {
        const r = list[idx]
        const reacted = !r.reacted
        const count = r.count + (reacted ? 1 : -1)
        if (count <= 0) list.splice(idx, 1)
        else list[idx] = { ...r, reacted, count }
      }
      return { ...s, [msgId]: list }
    })
    setReactionPicker(null)
  }

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
  const [, setProfileOpts] = useState<string[]>(PROFILE_OPTIONS)
  const [modelOpts, setModelOpts] = useState<string[]>(MODEL_OPTIONS)
  const [hermesSessions, setHermesSessions] = useState<PastSession[] | null>(null)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // ── Derive the active "agent" identity (header/avatar/colour) from live data.
  // `default` profile renders as "Hermes". The cron channel gets a synthetic
  // identity so the header/message rendering still works in read-only mode.
  const liveActive = liveAgents.find((a) => a.name === activeAgent)
  const agent = activeCron
    ? { name: 'Cron Jobs', role: 'Read-only · all scheduled jobs', color: '#9b8cff', icon: '◷' }
    : liveActive
      ? {
          name: liveActive.name === 'default' ? 'Hermes' : liveActive.name,
          role: liveActive.name === 'default' ? 'Coordinator' : liveActive.role,
          color: liveActive.color,
          icon: liveActive.avatar,
        }
      : { name: activeAgent === 'default' ? 'Hermes' : activeAgent, role: 'Coordinator', color: accent, icon: '⚕' }

  const thread = threads[activeAgent] || []
  const cronEpochWhen = (epoch: number) => {
    try { return new Date(epoch * 1000).toLocaleString() } catch { return '' }
  }
  const baseThread = activeCron
    ? (cronLoading
        ? [{ id: 'cron-loading', role: 'agent' as const, text: 'Loading cron output…', at: '' }]
        : cronOutput.length === 0
          ? [{ id: 'cron-empty', role: 'agent' as const, text: '(no recent cron output)', at: '' }]
          : cronOutput.map((m, i) => ({
              id: `cron-${m.job_id}-${i}`,
              role: 'agent' as const,
              text: `**[${m.job_id}]**${m.file ? ` ${m.file}` : ''}\n\n${m.content}`,
              at: cronEpochWhen(m.created_at),
            })))
    : viewSession
      ? viewSession.msgs.map((m, i) => ({ id: `v${i}`, ...m }))
      : activeAgent === 'default'
        ? thread
        : (() => {
            // Worker channel: Kanban task reports first, then any live chat.
            const reports = agentReports[activeAgent] || []
            if (reportsLoading && reports.length === 0) {
              return [{ id: 'reports-loading', role: 'agent' as const, text: 'Loading reports…', at: '' }]
            }
            return [...reports, ...thread]
          })()
  const displayThread = baseThread
  const pastList = activeAgent === 'default' && hermesSessions ? hermesSessions : (PAST_SESSIONS[activeAgent] || [])
  const ctxChars = thread.reduce((n, m) => n + m.text.length, 0)
  const ctxNum = Math.min(99, Math.round(ctxChars / 28))
  const ringDash = `${((Math.min(100, Math.round(ctxChars / 28)) / 100) * 56.55).toFixed(1)} 56.55`

  // Scroll to bottom whenever new messages arrive OR the panel becomes active.
  // When panel is hidden (display:none) scrollIntoView is a no-op, so we also
  // fire when isActive flips true so the first reveal lands at the bottom.
  useEffect(() => {
    if (displayThread.length === 0) return
    bottomRef.current?.scrollIntoView({ behavior: 'instant' })
  }, [displayThread.length, isActive])

  useEffect(() => {
    ;(async () => {
      try {
        const res = await fetch('/api/profiles')
        const data = await res.json() as string[]
        setProfileOpts(data)
      } catch { /* keep fallback */ }

      try {
        const res = await fetch('/api/agents')
        const data = await res.json() as LiveAgent[]
        setLiveAgents(Array.isArray(data) ? data : [])
      } catch { /* keep fallback */ }

      try {
        const res = await fetch('/api/cron')
        const data = await res.json() as CronJob[]
        setCronJobs(Array.isArray(data) ? data : [])
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
        const sorted = [...data].sort((a, b) => b.created_at - a.created_at)
        const sessions = sorted.map((s) => ({ id: s.id, title: s.title, when: epochToWhen(s.created_at), msgs: [] }))
        setHermesSessions(sessions)
        if (sessions.length > 0) {
          const savedId = localStorage.getItem('hermes-chat-last-session')
          const target = (savedId ? sessions.find(s => s.id === savedId) : null) ?? sessions[0]
          try {
            const msgRes = await fetch(`/api/chat/sessions/${target.id}/messages`)
            const msgs = await msgRes.json() as Message[]
            setViewSession({ ...target, msgs })
          } catch {
            setViewSession({ ...target, msgs: [] })
          }
          localStorage.setItem('hermes-chat-last-session', target.id)
        }
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

  // Bubble the total unread count up to Shell (drives the nav-rail badge).
  useEffect(() => {
    const total = Object.values(unreadCounts).reduce((a, b) => a + b, 0)
    onUnreadChange?.(total)
  }, [unreadCounts])

  // Request browser-notification permission once on mount (non-blocking).
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission().catch(() => {})
    }
  }, [])

  // When the Chat panel becomes active, clear all unread badges.
  useEffect(() => {
    if (isActive) setUnreadCounts((prev) => {
      if (Object.values(prev).every((v) => v === 0)) return prev
      return {}
    })
  }, [isActive])

  // Load a worker agent's Kanban task reports when its channel is selected.
  useEffect(() => {
    if (activeAgent === 'default' || activeCron) return
    let cancelled = false
    setReportsLoading(true)
    fetch(`/api/kanban/agent-reports/${activeAgent}`)
      .then(r => r.json())
      .then((msgs: any[]) => {
        if (cancelled) return
        const mapped: Message[] = (Array.isArray(msgs) ? msgs : []).map((m, i) => ({
          id: `report-${activeAgent}-${i}`,
          role: 'agent' as const,
          text: m.content,
          at: m.created_at ? new Date(m.created_at * 1000).toLocaleString() : '',
        }))
        setAgentReports(prev => ({ ...prev, [activeAgent]: mapped }))
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setReportsLoading(false) })
    return () => { cancelled = true }
  }, [activeAgent, activeCron])

  function selectAgent(key: string) {
    setActiveAgent(key)
    setActiveCron(null)
    setCronOutput([])
    setViewSession(null)
    setUnreadCounts((prev) => (prev[key] ? { ...prev, [key]: 0 } : prev))
  }

  async function selectCron() {
    setActiveCron('cron')
    setViewSession(null)
    setCronOutput([])
    setCronLoading(true)
    setUnreadCounts((prev) => (prev['cron'] ? { ...prev, cron: 0 } : prev))
    try {
      const res = await fetch('/api/cron/output')
      const data = await res.json() as CronOutputMsg[]
      setCronOutput(Array.isArray(data) ? data : [])
    } catch {
      setCronOutput([])
    } finally {
      setCronLoading(false)
    }
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

  // Called when an agent message completes. Increments the unread badge for
  // agents that aren't the active view, and fires a browser notification when
  // the window/tab is not focused. Resets the accumulated-text ref afterward.
  function notifyAgentMessage(k: string) {
    if (k !== activeAgent) {
      setUnreadCounts((prev) => ({ ...prev, [k]: (prev[k] || 0) + 1 }))
    }
    if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
      const agentLabel = k === 'default' ? 'Hermes' : k === 'cron' ? 'Cron Jobs' : k
      const preview = (lastMsgTextRef.current || '').slice(0, 80)
      try {
        const notif = new Notification(agentLabel, {
          body: preview || 'New message',
          icon: '/favicon.ico',
          tag: k,
        })
        notif.onclick = () => { window.focus() }
      } catch { /* notification construction can throw on some platforms */ }
    }
    lastMsgTextRef.current = ''
  }

  async function send() {
    const t = draft.trim()
    if ((!t && attachments.length === 0) || running) return
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

    // Build the augmented message (context notes for the agent) and a display
    // string (inline media tokens / filename badges for the user's own bubble).
    let augmented = t
    const displayParts: string[] = []
    for (const att of attachments) {
      if (att.is_image) {
        augmented = `[The user sent an image~ The file is also saved at: ${att.path}]\n\n${augmented}`
        displayParts.push(`MEDIA:${att.path}`)
      } else if (att.is_text && att.text_content) {
        augmented = `[The user sent a text document: '${att.filename}'. Its content has been included below. The file is also saved at: ${att.path}]\n\n${att.text_content}\n\n${augmented}`
        displayParts.push(`📄 ${att.filename}`)
      } else {
        augmented = `[The user sent a document: '${att.filename}'. It is saved at: ${att.path}. Its text is not inlined here (it's a binary format such as PDF or DOCX). To read it, extract the document's text yourself — for example with the terminal tool or the ocr-and-documents skill — before answering, instead of asking the user to paste the contents.]\n\n${augmented}`
        displayParts.push(`📄 ${att.filename}`)
      }
    }
    const displayText = [...displayParts, t].filter(Boolean).join('\n')
    setAttachments([])

    const k = activeAgent
    const at = nowTime()
    if (k === 'default') {
      setThreads((s) => ({ ...s, [k]: [...(s[k] || []), { id: 'u' + Date.now(), role: 'user', text: displayText, at }] }))
      setDraft('')
      setRunning(true)
      const controller = new AbortController()
      abortRef.current = controller
      let agentMsgId: string | null = null
      try {
        const res = await fetch('/api/chat/send', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, message: augmented, profile, model }),
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
              lastMsgTextRef.current += ev.text
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
              notifyAgentMessage(k)
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

  const avBg = `color-mix(in oklab, ${agent.color} 16%, transparent)`
  const avBorder = `color-mix(in oklab, ${agent.color} 42%, transparent)`

  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'row', minHeight: 0, animation: 'hpanelin 0.4s var(--ease-out)', overflow: 'hidden' }}>
      <ChatSidebar
        accent={accent}
        liveAgents={liveAgents}
        cronJobs={cronJobs}
        activeAgent={activeAgent}
        activeCron={activeCron}
        swarmOpen={swarmOpen}
        unreadCounts={unreadCounts}
        searchMode={searchMode}
        onToggleSwarm={() => setSwarmOpen((v) => !v)}
        onSelectAgent={selectAgent}
        onSelectCron={selectCron}
        onToggleSearch={() => (searchMode ? exitSearch() : setSearchMode(true))}
      />
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0, position: 'relative' }}>

      {/* ── Search overlay — replaces the message thread in search mode ──── */}
      {searchMode && (() => {
        const q = searchQuery.trim()
        const total = searchResults.sessions.length + searchResults.references.length + searchResults.skills.length
        const hasQuery = q.length >= 2
        const sectionHeader = (label: string, count: number) => (
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, padding: '14px 4px 6px' }}>
            <span style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ac)' }}>{label}</span>
            <span style={{ fontSize: 10.5, color: '#565d72' }}>{count} result{count === 1 ? '' : 's'}</span>
          </div>
        )
        const rowHover = (on: boolean) => (e: { currentTarget: HTMLElement }) => {
          e.currentTarget.style.background = on ? 'rgba(246,183,60,0.08)' : 'transparent'
        }
        return (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 1, background: 'rgba(18,18,28,0.9)', animation: 'hcmdin 0.18s cubic-bezier(0.16,1,0.3,1)' }}>
            {/* Search input */}
            <div style={{ flex: 'none', padding: '14px 22px 10px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#11151f', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, padding: '10px 13px' }}>
                <SearchIcon size={16} color="#9298ab" />
                <input
                  ref={searchInputRef}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); exitSearch() } }}
                  placeholder="Search messages, references, and skills…"
                  style={{ flex: 1, minWidth: 0, background: 'none', border: 'none', outline: 'none', color: '#e9ebf2', fontFamily: 'inherit', fontSize: 14 }}
                />
                {searchLoading && (
                  <span style={{ width: 15, height: 15, flex: 'none', borderRadius: '50%', border: '2px solid rgba(246,183,60,0.25)', borderTopColor: 'var(--ac)', animation: 'hspin 0.7s linear infinite' }} />
                )}
                <button
                  onClick={exitSearch}
                  title="Close search"
                  style={{ width: 22, height: 22, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'none', border: 'none', borderRadius: 6, cursor: 'pointer', color: '#6a7088' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#e9ebf2')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#6a7088')}
                >
                  <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round"><path d="M18 6L6 18M6 6l12 12" /></svg>
                </button>
              </div>
            </div>

            {/* Results */}
            <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', padding: '4px 22px 22px' }}>
              {!hasQuery ? (
                <div style={{ margin: 'auto', textAlign: 'center', padding: '60px 20px', color: '#6a7088', fontSize: 13, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 14 }}>
                  <SearchIcon size={34} color="#3a4055" />
                  <span>Search messages, references, and skills…</span>
                </div>
              ) : total === 0 && !searchLoading ? (
                <div style={{ margin: 'auto', textAlign: 'center', padding: '60px 20px', color: '#6a7088', fontSize: 13 }}>
                  No results for “{q}”
                </div>
              ) : (
                <>
                  {/* Sessions */}
                  {searchResults.sessions.length > 0 && (
                    <>
                      {sectionHeader('Sessions', searchResults.sessions.length)}
                      {searchResults.sessions.map((hit, i) => (
                        <div
                          key={`s-${hit.session_id}-${i}`}
                          onClick={() => handleSearchSessionClick(hit)}
                          onMouseEnter={rowHover(true)}
                          onMouseLeave={rowHover(false)}
                          style={{ padding: '10px 12px', borderRadius: 10, cursor: 'pointer', transition: 'background 0.14s' }}
                        >
                          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                            <span style={{ fontSize: 14, fontWeight: 600, color: '#f0f2f8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{hit.session_title}</span>
                            <span style={{ flex: 'none', fontSize: 11, color: '#6a7088' }}>{isoToWhen(hit.timestamp)}</span>
                          </div>
                          <div style={{ marginTop: 3, fontSize: 12.5, lineHeight: 1.5, color: '#9298ab', overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                            {renderSnippet(hit.snippet, accent)}
                          </div>
                        </div>
                      ))}
                    </>
                  )}

                  {/* References */}
                  {searchResults.references.length > 0 && (
                    <>
                      {sectionHeader('References', searchResults.references.length)}
                      {searchResults.references.map((hit, i) => {
                        const key = `r-${hit.path}-${i}`
                        const open = expandedHit === key
                        return (
                          <div
                            key={key}
                            onClick={() => setExpandedHit(open ? null : key)}
                            onMouseEnter={rowHover(true)}
                            onMouseLeave={rowHover(false)}
                            style={{ padding: '10px 12px', borderRadius: 10, cursor: 'pointer', transition: 'background 0.14s' }}
                          >
                            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                              <span style={{ fontSize: 13.5, fontWeight: 600, color: '#f0f2f8' }}>{hit.file}</span>
                              <span style={{ flex: 'none', fontSize: 11, color: '#565d72' }}>:{hit.line}</span>
                            </div>
                            <div style={{ marginTop: 3, fontFamily: 'IBM Plex Mono, monospace', fontSize: 12, lineHeight: 1.5, color: '#9298ab', whiteSpace: 'pre-wrap', wordBreak: 'break-word', ...(open ? {} : { overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }) }}>
                              {renderSnippet(hit.snippet, accent)}
                            </div>
                          </div>
                        )
                      })}
                    </>
                  )}

                  {/* Skills */}
                  {searchResults.skills.length > 0 && (
                    <>
                      {sectionHeader('Skills', searchResults.skills.length)}
                      {searchResults.skills.map((hit, i) => {
                        const key = `k-${hit.path}-${i}`
                        const open = expandedHit === key
                        return (
                          <div
                            key={key}
                            onClick={() => setExpandedHit(open ? null : key)}
                            onMouseEnter={rowHover(true)}
                            onMouseLeave={rowHover(false)}
                            style={{ padding: '10px 12px', borderRadius: 10, cursor: 'pointer', transition: 'background 0.14s' }}
                          >
                            <div style={{ fontSize: 13.5, fontWeight: 600, color: '#f0f2f8' }}>{hit.name}</div>
                            <div style={{ marginTop: 3, fontSize: 12.5, lineHeight: 1.5, color: '#9298ab', whiteSpace: 'pre-wrap', wordBreak: 'break-word', ...(open ? {} : { overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }) }}>
                              {renderSnippet(hit.snippet, accent)}
                            </div>
                          </div>
                        )
                      })}
                    </>
                  )}
                </>
              )}
            </div>
          </div>
        )
      })()}

      {!searchMode && (
      <div ref={listRef} style={{ flex: 1, minHeight: 0, overflowY: 'auto', scrollBehavior: 'auto', overflowX: 'hidden', padding: '14px 26px 22px', display: 'flex', flexDirection: 'column', gap: 0, position: 'relative', zIndex: 1 }}>
        {displayThread.length === 0 && !running && !reportsLoading ? (
          // Show true "loading" spinner only while sessions are still being fetched (null = in-flight)
          activeAgent === 'default' && hermesSessions === null ? (
            <div style={{ margin: 'auto', textAlign: 'center', padding: '40px 20px' }}>
              <span style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid rgba(246,183,60,0.25)', borderTopColor: 'var(--ac)', animation: 'hspin 0.7s linear infinite', display: 'inline-block' }} />
            </div>
          ) : pastList.length === 0 ? (
            // WELCOME SCREEN — first time ever, no sessions
            <div style={{
              margin: 'auto',
              textAlign: 'center',
              padding: '60px 20px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 0,
            }}>
              {/* Large golden Hermes icon */}
              <div style={{ fontSize: 56, lineHeight: 1, marginBottom: 20, color: agent.color, filter: 'drop-shadow(0 0 18px color-mix(in oklab, currentColor 55%, transparent))' }}>
                {agent.icon}
              </div>
              {/* Heading */}
              <div style={{ fontSize: 22, fontWeight: 700, color: '#ffffff', marginBottom: 10, letterSpacing: '-0.01em' }}>
                Chat with {agent.name} <span style={{ color: 'rgba(255,255,255,0.35)', fontWeight: 400 }}>·</span>
              </div>
              {/* Subtitle */}
              <div style={{ fontSize: 13, color: '#94a3b8', maxWidth: 340, lineHeight: 1.6 }}>
                • {agent.role} — send a message to start a conversation.
              </div>
            </div>
          ) : (
            // Sessions loaded, none selected — prompt user to pick one or start new
            <div style={{ margin: 'auto', textAlign: 'center', padding: '40px 20px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              <div style={{ fontSize: 32, color: agent.color, filter: 'drop-shadow(0 0 12px color-mix(in oklab, currentColor 45%, transparent))' }}>{agent.icon}</div>
              <div style={{ fontSize: 15, fontWeight: 600, color: '#e4e6ee' }}>Pick up where you left off</div>
              <div style={{ fontSize: 12, color: '#6a7088' }}>Select a past session from the list, or send a message to start a new one.</div>
            </div>
          )
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
                  (() => {
                    const isUser = m.role === 'user'
                    const senderName = isUser ? 'You' : agent.name
                    const avColor = isUser ? accent : agent.color
                    const rowAvBg = `color-mix(in oklab, ${avColor} 16%, transparent)`
                    const rowAvBorder = `color-mix(in oklab, ${avColor} 42%, transparent)`
                    return (
                      <div
                        style={{
                          padding: '14px 2px 16px',
                          borderBottom: '1px solid rgba(255,255,255,0.05)',
                        }}
                      >
                        {/* Sender header: avatar + name + timestamp */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
                          <span
                            style={{
                              width: 38, height: 38, flex: 'none', borderRadius: '50%',
                              display: 'flex', alignItems: 'center', justifyContent: 'center',
                              fontSize: 17, background: rowAvBg, border: `1px solid ${rowAvBorder}`,
                              color: avColor, fontFamily: 'var(--font-display)', fontWeight: 600,
                            }}
                          >
                            {isUser ? 'Y' : agent.icon}
                          </span>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: 1, minWidth: 0 }}>
                            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 14.5, color: '#f0f2f8' }}>
                              {senderName}
                            </span>
                            <span style={{ fontSize: 11, color: '#6a7088' }}>{m.at}</span>
                          </div>
                        </div>

                        {/* Body — larger, airier per reference */}
                        <div style={{ color: '#d8dbe6', wordWrap: 'break-word', paddingLeft: 50 }}>
                          <MessageContent text={m.text} accent={accent} />
                        </div>

                        {/* Status row — read tick on the user's own messages (decorative) */}
                        {isUser && (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginTop: 7, paddingLeft: 50, fontSize: 11.5, color: '#565d72' }}>
                            <StatusTick color={running && !viewSession && i === displayThread.length - 1 ? '#6a7088' : 'var(--success)'} />
                            <span>{m.at}</span>
                          </div>
                        )}

                        {/* Reaction pills + add-reaction affordance */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, paddingLeft: 50, flexWrap: 'wrap', position: 'relative' }}>
                          {(reactions[m.id] || []).map((r) => (
                            <button
                              key={r.emoji}
                              onClick={() => toggleReaction(m.id, r.emoji)}
                              title={r.reacted ? 'Remove reaction' : 'Add reaction'}
                              style={{
                                display: 'inline-flex', alignItems: 'center', gap: 4,
                                padding: '2px 9px', borderRadius: 99, cursor: 'pointer',
                                fontFamily: 'inherit', fontSize: 12, lineHeight: 1.4,
                                color: r.reacted ? 'var(--ac)' : '#9298ab',
                                background: r.reacted ? 'color-mix(in oklab, var(--ac) 15%, transparent)' : 'rgba(255,255,255,0.05)',
                                border: `1px solid ${r.reacted ? 'color-mix(in oklab, var(--ac) 42%, transparent)' : 'rgba(255,255,255,0.08)'}`,
                                transition: 'all 0.14s',
                              }}
                            >
                              <span>{r.emoji}</span>
                              <span className="mono" style={{ fontSize: 11 }}>{r.count}</span>
                            </button>
                          ))}
                          <button
                            onClick={() => setReactionPicker((p) => (p === m.id ? null : m.id))}
                            title="Add reaction"
                            style={{
                              width: 24, height: 24, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                              borderRadius: 99, cursor: 'pointer', border: '1px solid rgba(255,255,255,0.08)',
                              background: reactionPicker === m.id ? 'rgba(255,255,255,0.08)' : 'transparent',
                              color: reactionPicker === m.id ? '#e9ebf2' : '#565d72', transition: 'all 0.14s',
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.color = '#e9ebf2'; e.currentTarget.style.background = 'rgba(255,255,255,0.06)' }}
                            onMouseLeave={(e) => { if (reactionPicker !== m.id) { e.currentTarget.style.color = '#565d72'; e.currentTarget.style.background = 'transparent' } }}
                          >
                            <SmilePlusIcon size={14} />
                          </button>
                          {reactionPicker === m.id && (
                            <>
                              <div onClick={() => setReactionPicker(null)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
                              <div
                                style={{
                                  position: 'absolute', bottom: 'calc(100% + 6px)', left: 50, zIndex: 50,
                                  display: 'flex', gap: 2, padding: 5,
                                  background: '#0c1119', border: '1px solid rgba(255,255,255,0.12)',
                                  borderRadius: 12, boxShadow: '0 8px 28px rgba(0,0,0,0.55)',
                                  animation: 'hcmdin 0.15s cubic-bezier(0.16,1,0.3,1)',
                                }}
                              >
                                {REACTION_EMOJIS.map((emoji) => (
                                  <button
                                    key={emoji}
                                    onClick={() => toggleReaction(m.id, emoji)}
                                    style={{ width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, background: 'none', border: 'none', borderRadius: 8, cursor: 'pointer' }}
                                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.08)')}
                                    onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                                  >
                                    {emoji}
                                  </button>
                                ))}
                              </div>
                            </>
                          )}
                        </div>
                      </div>
                    )
                  })()
                )}
              </div>
            )
          })
        )}
        {running && !viewSession && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 2px 16px' }}>
            <span
              style={{
                width: 38, height: 38, flex: 'none', borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 17, background: avBg, border: `1px solid ${avBorder}`,
                color: agent.color, fontFamily: 'var(--font-display)', fontWeight: 600,
              }}
            >
              {agent.icon}
            </span>
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              {[0, 0.18, 0.36].map((d) => (
                <span key={d} style={{ width: 7, height: 7, borderRadius: '50%', background: '#9aa0b4', animation: `hbounce 1.3s ease-in-out ${d}s infinite` }} />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} style={{ height: 0, flexShrink: 0 }} />
      </div>
      )}
      {/* Composer — pinned to the bottom of the conversation column only */}
      {activeCron ? (
        <div style={{ flex: 'none', padding: '16px 22px 20px', position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9, padding: '14px 16px', background: '#11151f', border: '1px solid var(--tile-border)', borderRadius: 16, color: '#6a7088', fontSize: 13 }}>
            <ClockIcon size={15} color="#6a7088" />
            Read-only · Cron output
          </div>
        </div>
      ) : (
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
          {attachments.length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {attachments.map((att, i) => (
                <div
                  key={i}
                  style={{
                    position: 'relative', borderRadius: 8,
                    border: '1px solid var(--tile-border)',
                    overflow: 'hidden', background: 'rgba(255,255,255,0.04)',
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: att.is_image ? 0 : '6px 10px',
                    maxWidth: att.is_image ? 80 : 180,
                  }}
                >
                  {att.is_image && att.preview_url ? (
                    <img src={att.preview_url} alt={att.filename} style={{ width: 80, height: 80, objectFit: 'cover', display: 'block' }} />
                  ) : (
                    <span style={{ fontSize: 12, color: '#c6cad8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>📄 {att.filename}</span>
                  )}
                  <button
                    onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                    style={{
                      position: 'absolute', top: 2, right: 2,
                      background: 'rgba(0,0,0,0.6)', border: 'none',
                      color: '#fff', borderRadius: '50%', width: 18, height: 18,
                      fontSize: 11, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          )}
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
            onPaste={async (e) => {
              const items = Array.from(e.clipboardData?.items || [])
              const imageItem = items.find((i) => i.type.startsWith('image/'))
              if (!imageItem) return // let normal text paste through
              e.preventDefault()
              const blob = imageItem.getAsFile()
              if (!blob) return
              const fd = new FormData()
              fd.append('file', blob, `paste-${Date.now()}.png`)
              const res = await fetch('/api/chat/upload', { method: 'POST', body: fd })
              if (!res.ok) return
              const att: Attachment = await res.json()
              att.preview_url = URL.createObjectURL(blob)
              setAttachments((prev) => [...prev, att])
            }}
            placeholder={`Message ${agent.name}…`}
            style={{ width: '100%', resize: 'none', minHeight: 26, maxHeight: 140, background: 'none', border: 'none', color: '#e9ebf2', fontFamily: 'inherit', fontSize: 14, lineHeight: 1.5, outline: 'none' }}
          />
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', flex: 1, minWidth: 0 }}>
              {/* Hidden file input + paperclip attach button */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,.pdf,.txt,.md,.json,.csv,.docx,.xlsx"
                multiple
                style={{ display: 'none' }}
                onChange={async (e) => {
                  const files = Array.from(e.target.files || [])
                  for (const file of files) {
                    const fd = new FormData()
                    fd.append('file', file, file.name)
                    const res = await fetch('/api/chat/upload', { method: 'POST', body: fd })
                    if (!res.ok) continue
                    const att: Attachment = await res.json()
                    if (att.is_image) att.preview_url = URL.createObjectURL(file)
                    setAttachments((prev) => [...prev, att])
                  }
                  e.target.value = ''
                }}
              />
              <button
                aria-label="Attach file"
                title="Attach file"
                onClick={() => fileInputRef.current?.click()}
                style={{
                  width: 30, height: 30, flex: 'none', display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  background: 'none', border: 'none', borderRadius: 8,
                  color: '#6a7088', cursor: 'pointer', transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.color = '#e9ebf2'; e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = '#6a7088'; e.currentTarget.style.background = 'none' }}
              >
                <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" />
                </svg>
              </button>

              {/* Emoji insert button (ruixen SmilePlus, left of composer) */}
              <div style={{ position: 'relative', flex: 'none' }}>
                <button
                  title="Insert emoji"
                  onClick={() => setComposerEmoji((v) => !v)}
                  style={{
                    width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                    background: composerEmoji ? 'rgba(255,255,255,0.06)' : 'none',
                    border: 'none', borderRadius: 8,
                    color: composerEmoji ? '#e9ebf2' : '#6a7088', cursor: 'pointer', transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = '#e9ebf2'; e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
                  onMouseLeave={(e) => { if (!composerEmoji) { e.currentTarget.style.color = '#6a7088'; e.currentTarget.style.background = 'none' } }}
                >
                  <SmilePlusIcon size={16} />
                </button>
                {composerEmoji && (
                  <>
                    <div onClick={() => setComposerEmoji(false)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
                    <div
                      style={{
                        position: 'absolute', bottom: 'calc(100% + 8px)', left: 0, zIndex: 50,
                        display: 'flex', gap: 2, padding: 5,
                        background: '#0c1119', border: '1px solid rgba(255,255,255,0.12)',
                        borderRadius: 12, boxShadow: '0 8px 28px rgba(0,0,0,0.55)',
                        animation: 'hcmdin 0.15s cubic-bezier(0.16,1,0.3,1)',
                      }}
                    >
                      {REACTION_EMOJIS.map((emoji) => (
                        <button
                          key={emoji}
                          onMouseDown={(e) => { e.preventDefault(); setDraft((d) => d + emoji); setComposerEmoji(false) }}
                          style={{ width: 30, height: 30, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, background: 'none', border: 'none', borderRadius: 8, cursor: 'pointer' }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.08)')}
                          onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
                        >
                          {emoji}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>

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
                menuKey="model" value={model} options={modelOpts} open={composerMenu === 'model'} variant="pill" minWidth={190}
                onToggle={() => setComposerMenu((m) => (m === 'model' ? null : 'model'))}
                onPick={(v) => { setModel(v); localStorage.setItem('hermes-chat-model', v); setComposerMenu(null) }}
                icon={<svg width={14} height={14} viewBox="0 0 24 24" fill="none" stroke="#9298ab" strokeWidth={2}><circle cx={12} cy={12} r={3} /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></svg>}
              />
              <ComposerDropdown
                menuKey="reasoning" value={reason} options={REASON_OPTIONS} open={composerMenu === 'reasoning'} variant="pill" minWidth={160}
                onToggle={() => setComposerMenu((m) => (m === 'reasoning' ? null : 'reasoning'))}
                onPick={(v) => { setReason(v); localStorage.setItem('hermes-chat-reason', v); setComposerMenu(null) }}
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
      )}
    </div>{/* end right content col */}
  </div>
  )
}

// ── Chat panel ───────────────────────────────────────────────────────────────