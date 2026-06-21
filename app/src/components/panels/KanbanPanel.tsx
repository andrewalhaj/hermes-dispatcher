import { useMemo, useState } from 'react'
import {
  LANES,
  LANE_MAP,
  PROJ_META,
  fmtDur,
  initials,
  priColor,
  seedTasks,
  staleLevel,
  type LaneId,
  type Task,
} from '../../data/kanban'
import { useInfo } from '../TileInfoDrawer'

interface KanbanPanelProps {
  accent: string
}

/** Toast that auto-dismisses. */
function useToast() {
  const [toast, setToast] = useState<string | null>(null)
  const show = (msg: string) => {
    setToast(msg)
    window.clearTimeout((show as unknown as { _t?: number })._t)
    ;(show as unknown as { _t?: number })._t = window.setTimeout(() => setToast(null), 2600)
  }
  return { toast, show }
}

export default function KanbanPanel({ accent }: KanbanPanelProps) {
  const { openInfo } = useInfo()
  const [tasks, setTasks] = useState<Task[]>(() => seedTasks())
  const [search, setSearch] = useState('')
  const [tenantFilter, setTenantFilter] = useState<string>('all')
  const [projMenu, setProjMenu] = useState(false)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [dragOverCol, setDragOverCol] = useState<LaneId | null>(null)
  const [newTaskText, setNewTaskText] = useState('')
  const { toast, show } = useToast()

  const tenants = useMemo(() => [...new Set(tasks.map((t) => t.tenant))], [tasks])

  const projLabel = (v: string) => (v === 'all' ? 'Board' : PROJ_META[v]?.label || v)
  const projDot = (v: string) => (v === 'all' ? '#6a7088' : PROJ_META[v]?.dot || '#6a7088')
  const tenantCount = (v: string) => (v === 'all' ? tasks.length : tasks.filter((t) => t.tenant === v).length)

  const q = search.trim().toLowerCase()
  const visible = tasks.filter(
    (t) =>
      (!q || `${t.title} ${t.desc} ${t.tenant} ${t.skills.join(' ')}`.toLowerCase().includes(q)) &&
      (tenantFilter === 'all' || t.tenant === tenantFilter),
  )

  // Running is dispatcher-owned: never settable from the UI.
  function moveTask(id: string, status: LaneId) {
    if (status === 'running') {
      show('Running is dispatcher-owned — use Run dispatcher')
      return
    }
    setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, status, ageSec: 0 } : t)))
    setDraggingId(null)
    setDragOverCol(null)
  }

  function addTask() {
    const nt = newTaskText.trim()
    const title = nt || q || 'New task'
    const tenant = tenantFilter !== 'all' ? tenantFilter : 'internal'
    const task: Task = {
      id: `t${Date.now()}`,
      title,
      priority: 4,
      ageSec: 0,
      status: 'triage',
      tenant,
      assignee: null,
      skills: [],
      branch: '',
      desc: '',
    }
    setTasks((prev) => [task, ...prev])
    setNewTaskText('')
    show('Task created in Triage')
  }

  function runDispatcher() {
    // Mock: promote up to 3 ready tasks → running, assigning round-robin workers.
    const pool = ['w-okada-01', 'npc-builder', 'ops-bot']
    let i = 0
    let count = 0
    setTasks((prev) =>
      prev.map((t) => {
        if (t.status === 'ready' && i < pool.length) {
          count++
          return { ...t, status: 'running' as LaneId, assignee: pool[i++], ageSec: 0 }
        }
        return t
      }),
    )
    window.setTimeout(
      () => show(count ? `Dispatched ${count} task${count > 1 ? 's' : ''} → Running` : 'Nothing to dispatch · no ready tasks'),
      0,
    )
  }

  const dragging = !!draggingId

  return (
    <div className="relative flex flex-1 flex-col" style={{ minHeight: 0, minWidth: 0 }}>
      {/* Toolbar */}
      <div
        className="flex flex-none flex-wrap items-center"
        style={{ gap: '9px 11px', padding: '12px 22px 10px' }}
      >
        {/* Project dropdown title */}
        <div className="relative flex-none">
          {projMenu && (
            <div onClick={() => setProjMenu(false)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
          )}
          <button
            onClick={() => setProjMenu((v) => !v)}
            className="relative inline-flex items-baseline"
            style={{
              zIndex: 45,
              gap: 10,
              background: 'none',
              border: 'none',
              padding: '4px 8px 4px 7px',
              margin: 0,
              borderRadius: 9,
              cursor: 'pointer',
              fontFamily: 'inherit',
              transition: 'background 0.14s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.05)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
          >
            <span className="inline-flex items-baseline" style={{ gap: 10 }}>
              <span style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 19, letterSpacing: '-0.01em', color: '#f4f6fb' }}>
                {projLabel(tenantFilter)}
              </span>
              <span style={{ fontSize: 12, color: '#6a7088' }}>
                {visible.length} / {tasks.length}
              </span>
            </span>
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#6a7088"
              strokeWidth={2.2}
              strokeLinecap="round"
              strokeLinejoin="round"
              style={{ alignSelf: 'center', transform: projMenu ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
          {projMenu && (
            <div
              style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                zIndex: 46,
                marginTop: 7,
                minWidth: 220,
                background: '#0c1119',
                border: '1px solid rgba(255,255,255,0.12)',
                borderRadius: 11,
                padding: 6,
                boxShadow: '0 16px 40px rgba(0,0,0,0.5)',
                animation: 'hmenuup 0.16s ease',
              }}
            >
              {['all', ...tenants].map((v) => {
                const selected = tenantFilter === v
                return (
                  <div
                    key={v}
                    onClick={() => {
                      setTenantFilter(v)
                      setProjMenu(false)
                    }}
                    className="flex items-center justify-between"
                    style={{
                      gap: 12,
                      padding: '8px 11px',
                      borderRadius: 8,
                      fontSize: 12.5,
                      color: selected ? '#e9ebf2' : '#c6cad8',
                      cursor: 'pointer',
                      background: selected ? 'rgba(255,255,255,0.05)' : 'transparent',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.06)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = selected ? 'rgba(255,255,255,0.05)' : 'transparent')}
                  >
                    <span className="inline-flex items-center" style={{ gap: 9, minWidth: 0 }}>
                      <span style={{ width: 7, height: 7, borderRadius: 2, flex: 'none', background: projDot(v) }} />
                      {projLabel(v)}
                    </span>
                    <span className="inline-flex flex-none items-center" style={{ gap: 10 }}>
                      <span className="mono" style={{ fontSize: 11, color: '#6a7088' }}>{tenantCount(v)}</span>
                      {selected && (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth={2.6} strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 6 9 17l-5-5" />
                        </svg>
                      )}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Search */}
        <div className="relative" style={{ flex: '1 1 340px', minWidth: 240, maxWidth: 520 }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#666c82" strokeWidth={2} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)' }}>
            <circle cx="11" cy="11" r="7" />
            <path d="M21 21l-4.3-4.3" />
          </svg>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tasks, tenants…"
            style={{
              width: '100%',
              background: '#11151f',
              border: '1px solid rgba(255,255,255,0.09)',
              borderRadius: 8,
              padding: '8px 42px 8px 32px',
              color: '#e9ebf2',
              fontSize: 12.5,
              fontFamily: 'inherit',
              outline: 'none',
            }}
          />
          <button
            onClick={addTask}
            title="New task"
            className="inline-flex items-center justify-center"
            style={{
              position: 'absolute',
              right: 6,
              top: '50%',
              transform: 'translateY(-50%)',
              width: 26,
              height: 26,
              background: '#161b27',
              color: '#c6cad8',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 7,
              fontSize: 16,
              lineHeight: 1,
              cursor: 'pointer',
            }}
          >
            +
          </button>
        </div>

        {/* Run dispatcher */}
        <button
          onClick={runDispatcher}
          title="Run dispatcher"
          className="inline-flex flex-none items-center justify-center"
          style={{
            width: 34,
            height: 34,
            background: accent,
            color: '#1c1404',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            boxShadow: `0 4px 14px color-mix(in oklab, ${accent} 28%, transparent)`,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="#1c1404">
            <path d="M13 2L3 14h7v8l10-12h-7z" />
          </svg>
        </button>

        {/* Filters (tenant) */}
        <div className="relative">
          <select
            value={tenantFilter}
            onChange={(e) => setTenantFilter(e.target.value)}
            title="Filter by tenant"
            style={{
              background: '#11151f',
              color: '#c6cad8',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8,
              padding: '8px 13px',
              fontSize: 12,
              fontFamily: 'inherit',
              cursor: 'pointer',
              outline: 'none',
            }}
          >
            <option value="all">All tenants</option>
            {tenants.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Lanes */}
      <div
        className="flex flex-1 items-stretch"
        style={{
          minHeight: 0,
          overflowX: 'auto',
          overflowY: 'hidden',
          gap: 14,
          padding: '10px 26px 18px',
          backgroundImage: 'radial-gradient(rgba(255,255,255,0.035) 1px, transparent 0)',
          backgroundSize: '22px 22px',
          backgroundPosition: '-1px -1px',
        }}
      >
        {LANES.map((col) => {
          const colTasks = visible.filter((t) => t.status === col.id)
          const locked = col.id === 'running'
          const over = dragOverCol === col.id
          const forbidden = locked && dragging && over
          return (
            <div
              key={col.id}
              onDragOver={(e) => {
                if (locked) {
                  if (e.dataTransfer) e.dataTransfer.dropEffect = 'none'
                  if (dragOverCol !== col.id) setDragOverCol(col.id)
                  return
                }
                e.preventDefault()
                if (dragOverCol !== col.id) setDragOverCol(col.id)
              }}
              onDrop={(e) => {
                if (locked) {
                  show('Running is dispatcher-owned — use Run dispatcher')
                  return
                }
                e.preventDefault()
                if (draggingId) moveTask(draggingId, col.id)
              }}
              className="flex flex-none flex-col self-stretch"
              style={{
                width: 290,
                minHeight: 0,
                maxHeight: '100%',
                background: forbidden ? 'rgba(251,111,111,0.06)' : over && !locked ? `color-mix(in oklab, ${col.color} 9%, #0b0f18)` : '#0b0f18',
                border: `1px solid ${forbidden ? '#fb6f6f' : over && !locked ? col.color : 'rgba(255,255,255,0.07)'}`,
                borderStyle: forbidden ? 'dashed' : 'solid',
                borderRadius: 12,
                overflow: 'hidden',
                transition: 'border-color 0.12s, background 0.12s',
                boxShadow: over && !locked ? `0 0 0 1px ${col.color}, 0 8px 30px rgba(0,0,0,0.35)` : 'none',
              }}
            >
              {/* Lane header */}
              <div
                className="flex flex-none items-center justify-between"
                style={{ padding: '13px 15px 12px', background: `linear-gradient(180deg, ${col.color}12, transparent)`, borderBottom: '1px solid rgba(255,255,255,0.04)' }}
              >
                <div className="flex items-center" style={{ gap: 9 }}>
                  <span style={{ width: 9, height: 9, borderRadius: '50%', background: col.color, boxShadow: `0 0 9px ${col.color}` }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: '#dde0ea', letterSpacing: '0.01em' }}>{col.label}</span>
                  {locked && (
                    <span title="Dispatcher-owned — tasks enter via Run dispatcher" className="inline-flex" style={{ color: '#6a7088' }}>
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                        <rect x="5" y="11" width="14" height="9" rx="2" />
                        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
                      </svg>
                    </span>
                  )}
                </div>
                <span className="mono" style={{ fontSize: 11.5, color: '#8c92a6', background: 'rgba(255,255,255,0.06)', borderRadius: 8, padding: '2px 8px' }}>
                  {colTasks.length}
                </span>
              </div>

              {/* Cards */}
              <div className="flex flex-1 flex-col overflow-y-auto" style={{ minHeight: 0, padding: '10px 11px 13px', gap: 11 }}>
                {forbidden && (
                  <div style={{ border: '1px dashed #fb6f6f', background: 'rgba(251,111,111,0.09)', borderRadius: 9, padding: 11, textAlign: 'center', fontSize: 10.5, color: '#fb8c8c' }}>
                    Running is dispatcher-owned — use Run dispatcher
                  </div>
                )}
                {colTasks.map((t) => {
                  const pc = priColor(t.priority)
                  const stale = staleLevel(t.status, t.ageSec)
                  const staleColor = stale === 'red' ? '#fb6f6f' : stale === 'amber' ? '#f6b73c' : null
                  const age = fmtDur(t.ageSec)
                  return (
                    <div
                      key={t.id}
                      draggable
                      onDragStart={(e) => {
                        try {
                          e.dataTransfer.effectAllowed = 'move'
                          e.dataTransfer.setData('text/plain', t.id)
                        } catch {
                          /* noop */
                        }
                        setDraggingId(t.id)
                      }}
                      onDragEnd={() => {
                        setDraggingId(null)
                        setDragOverCol(null)
                      }}
                      onClick={() =>
                        openInfo({
                          category: `Task · ${LANE_MAP[t.status].label}`,
                          title: t.title,
                          accent: col.color,
                          desc: t.desc || 'No description yet.',
                          stats: [
                            { label: 'Tenant', value: t.tenant },
                            { label: 'Status', value: LANE_MAP[t.status].label },
                            { label: 'Priority', value: `P${t.priority}` },
                            { label: 'Assignee', value: t.assignee || 'unassigned' },
                            ...(t.branch ? [{ label: 'Branch', value: t.branch }] : []),
                            ...(age ? [{ label: 'In status', value: age }] : []),
                          ],
                        })
                      }
                      className="relative flex flex-none flex-col"
                      style={{
                        background: '#141a26',
                        border: `1px solid ${stale === 'red' ? 'rgba(251,111,111,0.45)' : stale === 'amber' ? 'rgba(246,183,60,0.32)' : 'rgba(255,255,255,0.07)'}`,
                        borderRadius: 10,
                        padding: '12px 13px',
                        paddingLeft: 'calc(13px + 3px)',
                        cursor: 'pointer',
                        opacity: draggingId === t.id ? 0.4 : 1,
                        gap: 9,
                        transition: 'transform 0.1s, border-color 0.12s, box-shadow 0.12s',
                        overflow: 'hidden',
                        boxShadow: stale === 'red' ? '0 0 0 1px rgba(251,111,111,0.4)' : 'none',
                        animation: 'hdropswap 0.24s cubic-bezier(0.16,1,0.3,1)',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)'
                        e.currentTarget.style.boxShadow = '0 6px 20px rgba(0,0,0,0.4)'
                        e.currentTarget.style.transform = 'translateY(-2px)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.borderColor = stale === 'red' ? 'rgba(251,111,111,0.45)' : stale === 'amber' ? 'rgba(246,183,60,0.32)' : 'rgba(255,255,255,0.07)'
                        e.currentTarget.style.boxShadow = stale === 'red' ? '0 0 0 1px rgba(251,111,111,0.4)' : 'none'
                        e.currentTarget.style.transform = 'none'
                      }}
                    >
                      <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 3, background: pc }} />
                      <div className="flex items-center" style={{ gap: 8 }}>
                        {t.priority !== 0 && (
                          <span className="mono" style={{ fontSize: 10, fontWeight: 500, color: pc, background: `${pc}1c`, border: `1px solid ${pc}33`, borderRadius: 5, padding: '1px 6px' }}>
                            P{t.priority}
                          </span>
                        )}
                        <span style={{ fontSize: 10.5, color: '#767c92', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.tenant}</span>
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.36, color: '#e4e6ee', textWrap: 'pretty' }}>{t.title}</div>
                      {t.skills.length > 0 && (
                        <div className="flex flex-wrap" style={{ gap: 5 }}>
                          {t.skills.slice(0, 3).map((sk) => (
                            <span key={sk} className="mono" style={{ fontSize: 9.5, color: '#8c92a6', background: 'rgba(255,255,255,0.045)', borderRadius: 5, padding: '2px 6px' }}>
                              {sk}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="flex items-center justify-between" style={{ marginTop: 1 }}>
                        <div className="flex items-center" style={{ gap: 11, fontSize: 11, color: '#6a7088' }}>
                          {age && (
                            <span
                              className="inline-flex items-center"
                              style={{ gap: 4, color: staleColor || '#6a7088', background: staleColor ? `${staleColor}1f` : 'transparent', borderRadius: 5, padding: '1px 6px' }}
                              title={`in ${LANE_MAP[t.status].label.toLowerCase()} for ${age}`}
                            >
                              {stale === 'red' && (
                                <span style={{ width: 5, height: 5, borderRadius: '50%', background: staleColor || '#fb6f6f', animation: 'hpulse 1.4s ease-in-out infinite' }} />
                              )}
                              {age}
                            </span>
                          )}
                        </div>
                        {t.assignee && (
                          <span
                            className="mono flex items-center justify-center"
                            style={{ fontSize: 9.5, fontWeight: 600, color: '#0a0e16', background: col.color, width: 21, height: 21, borderRadius: '50%', boxShadow: `0 0 0 2px color-mix(in oklab, ${col.color} 25%, transparent)` }}
                            title={t.assignee}
                          >
                            {initials(t.assignee)}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
                {colTasks.length === 0 && !forbidden && (
                  <div style={{ border: '1px dashed rgba(255,255,255,0.08)', borderRadius: 9, padding: 16, textAlign: 'center', fontSize: 11, color: '#4f566b' }}>empty</div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Toast */}
      {toast && (
        <div
          className="flex items-center"
          style={{
            position: 'fixed',
            left: '50%',
            bottom: 28,
            transform: 'translateX(-50%)',
            gap: 9,
            background: '#141a26',
            border: '1px solid rgba(255,255,255,0.14)',
            borderLeft: `3px solid ${accent}`,
            borderRadius: 10,
            padding: '12px 18px',
            fontSize: 13,
            color: '#e9ebf2',
            boxShadow: '0 16px 44px rgba(0,0,0,0.55)',
            animation: 'htoast 0.22s ease',
            zIndex: 50,
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill={accent}>
            <path d="M13 2L3 14h7v8l10-12h-7z" />
          </svg>
          {toast}
        </div>
      )}
    </div>
  )
}
