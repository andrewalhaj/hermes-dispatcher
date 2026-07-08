import { useEffect, useMemo, useState } from 'react'

interface SkillsProps {
  accent: string
}

interface SkillSummary {
  id: string
  name: string
  description: string
  category: string
  tags: string[]
  path: string
  enabled?: boolean
  version?: string
  author?: string
  last_modified?: string | null
}

interface SkillDetail {
  id: string
  name: string
  category: string
  path: string
  content: string
  enabled?: boolean
  version?: string
  author?: string
}

export default function Skills({ accent }: SkillsProps) {
  const [skills, setSkills] = useState<SkillSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [enabled, setEnabled] = useState<Record<string, boolean>>({})
  const [selId, setSelId] = useState<string | null>(null)
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState('')
  const [syncStatus, setSyncStatus] = useState<Record<string, string>>({})

  useEffect(() => {
    fetch('/api/skills?platform=telegram')
      .then((r) => r.json())
      .then((data: SkillSummary[]) => {
        setSkills(data)
        setEnabled(data.reduce((m, s) => { m[s.id] = s.enabled ?? true; return m }, {} as Record<string, boolean>))
        setLoading(false)
      })
      .catch((e: unknown) => { setError(String(e)); setLoading(false) })
  }, [])

  const toggle = async (id: string) => {
    const newState = !enabled[id]
    try {
      const res = await fetch(`/api/skills/${encodeURIComponent(id)}/enabled?platform=telegram`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newState }),
      })
      if (res.ok) {
        setEnabled((m) => ({ ...m, [id]: newState }))
        setSyncStatus((m) => ({ ...m, [id]: 'Synced' }))
        setTimeout(() => setSyncStatus((m) => ({ ...m, [id]: '' })), 2000)
        if (detail?.id === id) {
          setDetail((d) => (d ? { ...d, enabled: newState } : d))
        }
      } else {
        setSyncStatus((m) => ({ ...m, [id]: 'Error' }))
        setTimeout(() => setSyncStatus((m) => ({ ...m, [id]: '' })), 2000)
      }
    } catch (err) {
      setSyncStatus((m) => ({ ...m, [id]: 'Error' }))
      setTimeout(() => setSyncStatus((m) => ({ ...m, [id]: '' })), 2000)
    }
  }

  const openDrawer = (id: string) => {
    setSelId(id)
    setDetail(null)
    setEditMode(false)
    setSavedMsg('')
    setDetailLoading(true)
    fetch(`/api/skills/${encodeURIComponent(id)}`)
      .then((r) => r.json())
      .then((d: SkillDetail) => { setDetail(d); setDetailLoading(false) })
      .catch(() => setDetailLoading(false))
  }

  const closeDrawer = () => {
    setSelId(null)
    setDetail(null)
    setEditMode(false)
    setSavedMsg('')
  }

  const startEdit = () => {
    setEditContent(detail?.content ?? '')
    setEditMode(true)
    setSavedMsg('')
  }

  const cancelEdit = () => {
    setEditMode(false)
    setSavedMsg('')
  }

  const saveEdit = async () => {
    if (!selId) return
    setSaving(true)
    try {
      await fetch(`/api/skills/${encodeURIComponent(selId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: editContent }),
      })
      setDetail((d) => (d ? { ...d, content: editContent } : d))
      setEditMode(false)
      setSavedMsg('Saved')
      setTimeout(() => setSavedMsg(''), 2000)
    } finally {
      setSaving(false)
    }
  }

  const selSkill = useMemo(() => skills.find((s) => s.id === selId) ?? null, [skills, selId])
  const detailOn = selId ? (enabled[selId] ?? true) : false

  return (
    <div className="relative flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Skills</div>
        <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>tools the agent can call — click a skill for details, toggle to enable · <span style={{ color: '#f5a623' }}>changes take effect on next session</span></div>
      </header>

      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '22px 26px 32px' }}>
        {loading && <div style={{ color: '#6a7088', fontSize: 13 }}>Loading skills…</div>}
        {error && <div style={{ color: '#f87171', fontSize: 13 }}>Error: {error}</div>}
        <div style={{ maxWidth: 1080, margin: '0 auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14, animation: 'hcellin 0.45s ease backwards', animationDelay: '0s' }}>
          {skills.map((p, i) => {
            const on = enabled[p.id] ?? true
            const sel = selId === p.id
            const selBorder = sel ? accent : on ? `color-mix(in oklab, ${accent} 28%, transparent)` : 'rgba(255,255,255,0.06)'
            return (
              <div
                key={p.id}
                onClick={() => openDrawer(p.id)}
                className="flex flex-col"
                style={{
                  background: 'var(--s3)',
                  border: `1px solid ${selBorder}`,
                  borderRadius: 12,
                  padding: 16,
                  gap: 11,
                  cursor: 'pointer',
                  transition: 'transform 0.28s cubic-bezier(0.16,1,0.3,1), border-color 0.28s, box-shadow 0.28s',
                  animation: 'hcellin 0.45s ease backwards',
                  animationDelay: `${i * 0.07}s`,
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-4px)'
                  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.28)'
                  e.currentTarget.style.boxShadow = '0 14px 34px rgba(0,0,0,0.45)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'none'
                  e.currentTarget.style.borderColor = selBorder
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                <div className="flex items-start" style={{ gap: 11 }}>
                  <span style={{ width: 8, height: 8, borderRadius: '50%', background: on ? '#4ade80' : '#565d72', marginTop: 6, flex: 'none', boxShadow: `0 0 8px ${on ? '#4ade80' : '#565d72'}` }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="flex items-center" style={{ gap: 8 }}>
                      <span style={{ fontSize: 14, fontWeight: 600, color: '#f0f2f8' }}>{p.name}</span>
                      <span style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#818799', background: 'rgba(255,255,255,0.05)', borderRadius: 5, padding: '2px 6px' }}>{p.category}</span>
                    </div>
                    <div style={{ fontSize: 12.5, lineHeight: 1.5, color: '#9aa0b4', marginTop: 5 }}>{p.description}</div>
                  </div>
                  <div className="flex flex-col items-end" style={{ gap: 6 }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); toggle(p.id) }}
                      aria-label={`${on ? 'Disable' : 'Enable'} ${p.name}`}
                      className="relative flex-none"
                      style={{ width: 38, height: 22, borderRadius: 12, border: 'none', background: on ? accent : 'rgba(255,255,255,0.12)', cursor: 'pointer', transition: 'background 0.15s' }}
                    >
                      <span style={{ position: 'absolute', top: 2, left: on ? 18 : 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', transition: 'left 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.4)' }} />
                    </button>
                    {syncStatus[p.id] && (
                      <span style={{ fontSize: 9, color: syncStatus[p.id] === 'Synced' ? '#4ade80' : '#f87171', opacity: syncStatus[p.id] ? 1 : 0, transition: 'opacity 0.2s' }}>
                        {syncStatus[p.id]}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap" style={{ gap: 5 }}>
                  {p.tags.map((k) => (
                    <span key={k} className="mono" style={{ fontSize: 10, color: '#9298ab', background: 'rgba(255,255,255,0.045)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 5, padding: '2px 7px' }}>
                      {k}
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {selId && (
        <>
          <div
            onClick={closeDrawer}
            style={{ position: 'absolute', inset: 0, zIndex: 30, background: 'rgba(4,6,10,0.5)', backdropFilter: 'blur(2px)', animation: 'hscrimin 0.2s ease' }}
          />
          <div
            className="flex flex-col"
            style={{
              position: 'absolute', top: 0, right: 0, bottom: 0, zIndex: 31,
              width: 452, maxWidth: '90%', background: '#0b0f17',
              borderLeft: '1px solid var(--tile-border)',
              boxShadow: '-22px 0 60px rgba(0,0,0,0.5)',
              minHeight: 0, animation: 'hdrawerin 0.3s cubic-bezier(0.16,1,0.3,1)',
            }}
          >
            <div style={{ flex: 'none', height: 3, background: accent, boxShadow: `0 0 16px ${accent}` }} />
            <div className="flex flex-none items-start justify-between" style={{ gap: 14, padding: '20px 22px 0' }}>
              <div style={{ minWidth: 0 }}>
                <span style={{ display: 'inline-block', fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#818799', background: 'rgba(255,255,255,0.05)', borderRadius: 5, padding: '3px 7px' }}>
                  {selSkill?.category ?? detail?.category ?? ''}
                </span>
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 25, letterSpacing: '0.01em', color: 'var(--text-primary)', marginTop: 11 }}>
                  {selSkill?.name ?? detail?.name ?? selId}
                </div>
                <div
                  className="inline-flex items-center"
                  style={{ gap: 7, marginTop: 9, fontSize: 11, fontWeight: 600, color: detailOn ? '#4ade80' : '#6a7088', background: detailOn ? 'rgba(74,222,128,0.12)' : 'rgba(255,255,255,0.05)', borderRadius: 7, padding: '4px 9px' }}
                >
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: detailOn ? '#4ade80' : '#6a7088', boxShadow: `0 0 7px ${detailOn ? '#4ade80' : '#6a7088'}` }} />
                  {detailOn ? 'Enabled' : 'Disabled'}
                </div>
                {detail && (
                  <div style={{ marginTop: 12, fontSize: 11, color: '#9aa0b4' }}>
                    {detail.version && <div style={{ marginBottom: 4 }}>Version: <span style={{ color: '#c8cce0' }}>{detail.version}</span></div>}
                    {detail.author && <div style={{ marginBottom: 4 }}>Author: <span style={{ color: '#c8cce0' }}>{detail.author}</span></div>}
                  </div>
                )}
              </div>
              <button
                onClick={closeDrawer}
                className="inline-flex flex-none items-center justify-center"
                style={{ width: 32, height: 32, background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 9, color: '#9aa0b4', cursor: 'pointer', transition: 'color 0.15s, background 0.15s' }}
                onMouseEnter={(e) => { e.currentTarget.style.color = '#f4f6fb'; e.currentTarget.style.background = 'rgba(255,255,255,0.1)' }}
                onMouseLeave={(e) => { e.currentTarget.style.color = '#9aa0b4'; e.currentTarget.style.background = 'rgba(255,255,255,0.05)' }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '20px 22px 26px' }}>
              {detailLoading && <div style={{ color: '#6a7088', fontSize: 13 }}>Loading…</div>}

              {!detailLoading && detail && !editMode && (
                <>
                  <pre style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 11.5, lineHeight: 1.6, color: '#c8cce0', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, padding: 16, whiteSpace: 'pre-wrap', wordBreak: 'break-word', overflowX: 'hidden', margin: 0 }}>
                    {detail.content}
                  </pre>
                  <div className="flex items-center" style={{ gap: 10, marginTop: 16 }}>
                    <button
                      onClick={startEdit}
                      style={{ padding: '7px 16px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.05)', color: '#d4d8e4', fontSize: 12.5, fontFamily: 'inherit', fontWeight: 600, cursor: 'pointer', transition: 'background 0.15s' }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.1)')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
                    >
                      Edit
                    </button>
                    {savedMsg && <span style={{ fontSize: 12, color: '#4ade80' }}>{savedMsg}</span>}
                  </div>
                </>
              )}

              {!detailLoading && editMode && (
                <>
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    style={{ width: '100%', minHeight: 380, fontFamily: 'var(--font-mono, monospace)', fontSize: 11.5, lineHeight: 1.6, color: '#c8cce0', background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 10, padding: 16, resize: 'vertical', boxSizing: 'border-box' }}
                  />
                  <div className="flex items-center" style={{ gap: 10, marginTop: 12 }}>
                    <button
                      onClick={saveEdit}
                      disabled={saving}
                      style={{ padding: '7px 16px', borderRadius: 8, border: 'none', background: accent, color: '#1c1404', fontSize: 12.5, fontFamily: 'inherit', fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.7 : 1 }}
                    >
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button
                      onClick={cancelEdit}
                      disabled={saving}
                      style={{ padding: '7px 16px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.05)', color: '#9aa0b4', fontSize: 12.5, fontFamily: 'inherit', cursor: 'pointer' }}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              )}

              <button
                onClick={() => toggle(selId)}
                className="flex w-full items-center justify-center"
                style={{
                  gap: 10, marginTop: 22, padding: 12, borderRadius: 11,
                  background: detailOn ? 'rgba(255,255,255,0.05)' : accent,
                  border: detailOn ? '1px solid rgba(255,255,255,0.12)' : '1px solid transparent',
                  color: detailOn ? '#c6cad8' : '#1c1404',
                  fontFamily: 'inherit', fontSize: 13, fontWeight: 600,
                  cursor: 'pointer', transition: 'filter 0.15s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.filter = 'brightness(1.08)')}
                onMouseLeave={(e) => (e.currentTarget.style.filter = 'none')}
              >
                <span className="relative flex-none" style={{ width: 38, height: 22, borderRadius: 12, background: detailOn ? accent : 'rgba(255,255,255,0.18)', transition: 'background 0.15s' }}>
                  <span style={{ position: 'absolute', top: 2, left: detailOn ? 18 : 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', transition: 'left 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.4)' }} />
                </span>
                {detailOn ? 'Disable skill' : 'Enable skill'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
