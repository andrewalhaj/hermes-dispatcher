import { useEffect, useState } from 'react'
import { ACCENT } from '../../data/agents'
import { galaxyDecor } from '../../data/phase3'
import type { GalaxyData, GalaxySelection, MemNode } from '../../data/phase3'
import { useGalaxy } from '../memory/useGalaxy'
import { fetchGalaxyData } from '../../data/memoryGalaxy'
import '../../styles/phase3.css'

interface MemoryProps {
  accent?: string
}

interface FilesData {
  memory: string
  user: string
  soul: string
  agents: string
  memory_chars: number
  user_chars: number
  memory_cap: number
  user_cap: number
}

interface EditorPanelProps {
  label: string
  subtitle: string
  value: string
  onChange: (v: string) => void
  chars: number
  cap: number
  status: string
  onSave: () => void
  accent: string
}

function EditorPanel({ label, subtitle, value, onChange, chars, cap, status, onSave, accent }: EditorPanelProps) {
  const pct = cap > 0 ? chars / cap : 0
  const pctStr = (pct * 100).toFixed(1) + '%'
  const charColor = pct >= 1 ? '#fb6f6f' : pct >= 0.9 ? '#f6b73c' : '#6a7088'
  const saved = status.includes('✓')
  const errored = status.includes('✗')

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--s2)', border: '1px solid var(--border)', borderRadius: 12, padding: 16, gap: 10 }}>
      <div className="flex items-center justify-between" style={{ flexWrap: 'wrap', gap: 8 }}>
        <div>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>{label}</div>
          <div className="mono" style={{ fontSize: 10, color: '#6a7088', marginTop: 2 }}>{subtitle}</div>
        </div>
        <div className="flex items-center" style={{ gap: 10 }}>
          <span className="mono" style={{ fontSize: 11, color: charColor }}>{chars} / {cap} ({pctStr})</span>
          {status && (
            <span style={{ fontSize: 11, color: saved ? '#4ade80' : errored ? '#fb6f6f' : '#6a7088' }}>{status}</span>
          )}
          <button
            onClick={onSave}
            style={{
              background: `color-mix(in oklab, ${accent} 18%, transparent)`,
              border: `1px solid color-mix(in oklab, ${accent} 40%, transparent)`,
              color: accent,
              borderRadius: 7,
              padding: '4px 12px',
              fontSize: 11,
              fontWeight: 600,
              cursor: 'pointer',
              fontFamily: 'inherit',
            }}
          >
            Save
          </button>
        </div>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        style={{
          flex: 1,
          minHeight: 260,
          resize: 'none',
          background: 'rgba(0,0,0,0.25)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 8,
          padding: '10px 12px',
          color: 'var(--text-primary)',
          fontFamily: 'IBM Plex Mono, ui-monospace, monospace',
          fontSize: 12,
          lineHeight: 1.65,
          outline: 'none',
        }}
      />
    </div>
  )
}

export default function Memory({ accent = ACCENT }: MemoryProps) {
  const [tab, setTab] = useState<'galaxy' | 'editor'>('galaxy')

  // Galaxy state
  const [galaxyData, setGalaxyData] = useState<GalaxyData>({ nodes: [], links: [], tiers: [] })
  const [galaxyLoading, setGalaxyLoading] = useState(true)
  const [paused, setPaused] = useState(false)
  const [sel, setSel] = useState<GalaxySelection | null>(null)

  // Editor state
  const [filesData, setFilesData] = useState<FilesData | null>(null)
  const [memContent, setMemContent] = useState('')
  const [userContent, setUserContent] = useState('')
  const [soulContent, setSoulContent] = useState('')
  const [agentsContent, setAgentsContent] = useState('')
  const [memStatus, setMemStatus] = useState('')
  const [userStatus, setUserStatus] = useState('')
  const [soulStatus, setSoulStatus] = useState('')
  const [agentsStatus, setAgentsStatus] = useState('')

  const onSelect = (node: MemNode) => setSel(galaxyDecor(node))
  // Keep canvas always mounted (hidden behind editor) so the RAF loop persists
  const canvasRef = useGalaxy({ data: galaxyData, paused, selectedId: sel?.id ?? null, onSelect })

  // Fetch galaxy data on mount
  useEffect(() => {
    setGalaxyLoading(true)
    fetchGalaxyData()
      .then(setGalaxyData)
      .catch(() => {/* silently show empty galaxy on network error */})
      .finally(() => setGalaxyLoading(false))
  }, [])

  // Fetch editor files when editor tab is first opened
  useEffect(() => {
    if (tab !== 'editor' || filesData !== null) return
    fetch('/api/memory/files')
      .then((r) => r.json())
      .then((d: FilesData) => {
        setFilesData(d)
        setMemContent(d.memory)
        setUserContent(d.user)
        setSoulContent(d.soul ?? '')
        setAgentsContent(d.agents ?? '')
      })
      .catch(() => {/* leave empty on error */})
  }, [tab, filesData])

  // Spacebar toggles pause — ignored while focus is in an input/textarea/select
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.code === 'Space' || e.key === ' ') {
        const t = e.target as HTMLElement | null
        if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return
        e.preventDefault()
        setPaused((p) => !p)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const saveFile = async (file: 'memory' | 'user' | 'soul' | 'agents') => {
    const contentMap = { memory: memContent, user: userContent, soul: soulContent, agents: agentsContent }
    const statusSetters = { memory: setMemStatus, user: setUserStatus, soul: setSoulStatus, agents: setAgentsStatus }
    const content = contentMap[file]
    const setStatus = statusSetters[file]
    try {
      const res = await fetch('/api/memory/files', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file, content }),
      })
      if (!res.ok) throw new Error('Save failed')
      const data: { ok: boolean; chars: number } = await res.json()
      setStatus('Saved ✓')
      setFilesData((prev) =>
        prev
          ? file === 'memory'
            ? { ...prev, memory_chars: data.chars }
            : file === 'user'
              ? { ...prev, user_chars: data.chars }
              : prev
          : prev
      )
    } catch {
      setStatus('Error ✗')
    } finally {
      setTimeout(() => setStatus(''), 2500)
    }
  }

  const pauseDot = paused ? accent : '#4ade80'
  const pauseLabel = paused ? 'Paused' : 'Orbiting'

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      {/* Header */}
      <header
        className="flex flex-wrap items-center justify-between"
        style={{ flex: 'none', padding: '14px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)', gap: 16 }}
      >
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>
            Memory Galaxy
          </div>
          <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>
            {tab === 'galaxy'
              ? `${galaxyData.nodes.length} memories · drag to orbit · scroll to zoom · click a star to inspect · space to pause`
              : 'Edit MEMORY.md and USER.md directly'}
          </div>
        </div>

        <div className="flex flex-wrap items-center" style={{ gap: 7 }}>
          {/* Tab bar */}
          {(['galaxy', 'editor'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                background: tab === t ? `color-mix(in oklab, ${accent} 15%, transparent)` : 'var(--s4)',
                border: `1px solid ${tab === t ? accent : 'var(--border)'}`,
                color: tab === t ? accent : 'var(--text-muted)',
                borderRadius: 7,
                padding: '4px 13px',
                fontSize: 11,
                fontWeight: 600,
                cursor: 'pointer',
                fontFamily: 'inherit',
                transition: 'border-color 0.15s, color 0.15s',
              }}
            >
              {t === 'galaxy' ? 'Galaxy' : 'Editor'}
            </button>
          ))}

          {/* Tier legend — only on galaxy tab */}
          {tab === 'galaxy' &&
            galaxyData.tiers.map((t) => (
              <span
                key={t.id}
                className="inline-flex items-center"
                style={{ gap: 6, fontSize: 11, color: 'var(--text-muted)', background: 'var(--s4)', border: '1px solid var(--border)', borderRadius: 7, padding: '4px 9px' }}
              >
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: t.color, boxShadow: `0 0 7px ${t.color}` }} />
                {t.label} <span className="mono" style={{ color: '#6a7088' }}>{t.count}</span>
              </span>
            ))}
        </div>
      </header>

      {/* Galaxy canvas — always mounted, visibility toggled to keep RAF alive */}
      <div
        className="relative"
        style={{ flex: tab === 'galaxy' ? 1 : 0, minHeight: 0, overflow: 'hidden', display: tab === 'galaxy' ? 'block' : 'none' }}
      >
        <canvas ref={canvasRef} style={{ display: 'block', width: '100%', height: '100%', cursor: 'grab' }} />

        {/* Loading overlay */}
        {galaxyLoading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6a7088', fontSize: 13 }}>
            Loading memory data…
          </div>
        )}

        {/* Pause pill */}
        <button
          onClick={() => setPaused((p) => !p)}
          className="inline-flex items-center"
          style={{ position: 'absolute', left: 22, top: 18, zIndex: 5, gap: 8, background: 'rgba(12,17,25,0.78)', backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, padding: '7px 12px', fontFamily: 'inherit', fontSize: 11.5, fontWeight: 600, color: '#c6cad8', cursor: 'pointer', transition: 'border-color 0.15s' }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.26)')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255,255,255,0.1)')}
        >
          <span style={{ width: 7, height: 7, borderRadius: '50%', background: pauseDot, boxShadow: `0 0 7px ${pauseDot}` }} />
          {pauseLabel}
        </button>

        {/* Selected node info card */}
        {sel && (
          <div
            style={{ position: 'absolute', right: 22, bottom: 22, width: 300, background: 'rgba(13,18,28,0.92)', backdropFilter: 'blur(10px)', border: '1px solid rgba(255,255,255,0.12)', borderLeft: `3px solid ${sel.color}`, borderRadius: 12, padding: 16, boxShadow: '0 16px 40px rgba(0,0,0,0.5)', zIndex: 6, animation: 'hdrawerin 0.24s var(--ease-out)' }}
          >
            <div className="flex items-center justify-between" style={{ gap: 10 }}>
              <span
                className="inline-flex items-center"
                style={{ gap: 7, fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.06em', color: sel.color }}
              >
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: sel.color, boxShadow: `0 0 8px ${sel.color}` }} />
                {sel.tierLabel}
              </span>
              <button
                onClick={() => setSel(null)}
                style={{ background: 'none', border: 'none', color: '#818799', fontSize: 17, lineHeight: 1, cursor: 'pointer', padding: 0 }}
                onMouseEnter={(e) => (e.currentTarget.style.color = '#e9ebf2')}
                onMouseLeave={(e) => (e.currentTarget.style.color = '#818799')}
              >
                ×
              </button>
            </div>
            <div style={{ fontSize: 14.5, fontWeight: 600, color: '#f0f2f8', marginTop: 10, lineHeight: 1.35 }}>{sel.title}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 7, lineHeight: 1.55 }}>{sel.detail}</div>
            <div className="flex items-center" style={{ gap: 18, marginTop: 14, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
              {[
                { l: 'Importance', v: sel.importance },
                { l: 'Recall', v: sel.recall },
                { l: 'Age', v: sel.age },
              ].map((x) => (
                <div key={x.l}>
                  <div style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088' }}>{x.l}</div>
                  <div className="mono" style={{ fontSize: 13, color: '#e4e6ee', marginTop: 2 }}>{x.v}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Editor tab */}
      {tab === 'editor' && (
        <div
          style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '20px 26px', display: 'flex', gap: 20, flexWrap: 'wrap' }}
        >
          <EditorPanel
            label="Memory"
            subtitle="default · MEMORY.md"
            value={memContent}
            onChange={setMemContent}
            chars={memContent.length}
            cap={filesData?.memory_cap ?? 2200}
            status={memStatus}
            onSave={() => saveFile('memory')}
            accent={accent}
          />
          <EditorPanel
            label="User Profile"
            subtitle="default · USER.md"
            value={userContent}
            onChange={setUserContent}
            chars={userContent.length}
            cap={filesData?.user_cap ?? 1375}
            status={userStatus}
            onSave={() => saveFile('user')}
            accent={accent}
          />
          <EditorPanel
            label="Soul"
            subtitle="default · SOUL.md"
            value={soulContent}
            onChange={setSoulContent}
            chars={soulContent.length}
            cap={99999}
            status={soulStatus}
            onSave={() => saveFile('soul')}
            accent={accent}
          />
          <EditorPanel
            label="Agents"
            subtitle="default · AGENTS.md"
            value={agentsContent}
            onChange={setAgentsContent}
            chars={agentsContent.length}
            cap={99999}
            status={agentsStatus}
            onSave={() => saveFile('agents')}
            accent={accent}
          />
        </div>
      )}
    </div>
  )
}
