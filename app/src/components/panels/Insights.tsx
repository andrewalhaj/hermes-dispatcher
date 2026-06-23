import React, { useState, useEffect } from 'react'
import { ACCENT } from '../../data/agents'
import type { InfoObject } from '../../data/info'
import { useInfo } from '../TileInfoDrawer'
import '../../styles/phase3.css'

interface InsightsAPI {
  tasks_today: number
  tasks_week: number
  success_rate: number
  avg_latency_s: number
  by_profile: Array<{ profile: string; completed: number; running: number; success_rate: number }>
  sessions_today: number
  messages_today: number
  kanban_throughput: Array<{ date: string; completed: number }>
  top_skills: Array<{ skill: string; count: number }>
  tokens_input?: number
  tokens_output?: number
}

interface InsightsProps {
  accent?: string
}

const cardLabel: React.CSSProperties = { fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6a7088' }
const cardBase: React.CSSProperties = {
  background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 14, padding: 18,
  transition: 'transform 0.28s cubic-bezier(0.16,1,0.3,1), border-color 0.28s, box-shadow 0.28s', cursor: 'pointer',
}

function hoverIn(e: React.MouseEvent<HTMLElement>) {
  e.currentTarget.style.transform = 'translateY(-4px)'
  e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)'
  e.currentTarget.style.boxShadow = '0 14px 34px rgba(0,0,0,0.45)'
}
function hoverOut(e: React.MouseEvent<HTMLElement>) {
  e.currentTarget.style.transform = 'none'
  e.currentTarget.style.borderColor = 'var(--border)'
  e.currentTarget.style.boxShadow = 'none'
}

function fmtNum(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

export default function Insights({ accent = ACCENT }: InsightsProps) {
  const [data, setData] = useState<InsightsAPI | null>(null)
  const [error, setError] = useState(false)
  const { openInfo } = useInfo()
  const open = openInfo

  useEffect(() => {
    let cancelled = false
    async function fetchData() {
      try {
        const res = await fetch('/api/insights')
        if (!res.ok) throw new Error('non-ok')
        const json: InsightsAPI = await res.json()
        if (!cancelled) { setData(json); setError(false) }
      } catch (_err) {
        if (!cancelled) setError(true)
      }
    }
    fetchData()
    const id = setInterval(fetchData, 30000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  if (!data) {
    return (
      <div className="flex flex-1 items-center justify-center" style={{ color: error ? '#f6b73c' : '#6a7088', fontSize: 14 }}>
        {error ? 'Could not load insights' : 'Loading analytics…'}
      </div>
    )
  }

  // KPI tiles
  const kpis: Array<{ label: string; value: string; accent: string; info: InfoObject }> = [
    {
      label: 'Tasks Today', value: String(data.tasks_today), accent,
      info: { category: 'Tasks', title: 'Tasks Today', accent, value: String(data.tasks_today), desc: 'Tasks dispatched and run today across all agents.', stats: [{ label: 'This Week', value: String(data.tasks_week) }, { label: 'Success Rate', value: `${data.success_rate}%` }] },
    },
    {
      label: 'Sessions Today', value: String(data.sessions_today), accent: '#5aa2f0',
      info: { category: 'Sessions', title: 'Sessions Today', accent: '#5aa2f0', value: String(data.sessions_today), desc: 'Chat and worker sessions opened today.', stats: [{ label: 'Messages', value: fmtNum(data.messages_today) }] },
    },
    {
      label: 'Messages Today', value: fmtNum(data.messages_today), accent: '#2dd4bf',
      info: { category: 'Messages', title: 'Messages Today', accent: '#2dd4bf', value: fmtNum(data.messages_today), desc: 'Messages exchanged with Hermes and worker agents today.', stats: [] },
    },
    {
      label: 'Success Rate', value: `${data.success_rate}%`, accent: '#9b8cff',
      info: { category: 'Quality', title: 'Success Rate', accent: '#9b8cff', value: `${data.success_rate}%`, desc: 'Share of tasks that finished without error over the trailing window.', stats: [{ label: 'Tasks Today', value: String(data.tasks_today) }] },
    },
    {
      label: 'Avg Latency', value: `${data.avg_latency_s}s`, accent: '#f6b73c',
      info: { category: 'Latency', title: 'Avg Latency', accent: '#f6b73c', value: `${data.avg_latency_s}s`, desc: 'Mean end-to-end time from dispatch to first result across recent tasks.', stats: [] },
    },
  ]

  // Activity by day bars
  const maxCompleted = Math.max(...data.kanban_throughput.map(d => d.completed), 1)
  const bars = data.kanban_throughput.map(d => ({
    date: d.date,
    h: `${Math.max(d.completed > 0 ? 8 : 3, Math.round((d.completed / maxCompleted) * 90))}px`,
    bg: d.completed > 0 ? 'var(--ac)' : 'rgba(255,255,255,0.07)',
  }))
  const peakEntry = data.kanban_throughput.length > 0
    ? data.kanban_throughput.reduce((a, b) => b.completed > a.completed ? b : a)
    : { date: '—', completed: 0 }
  const activityInfo: InfoObject = {
    category: 'Activity', title: 'Activity by Day', accent,
    desc: 'Kanban tasks completed per day over the last 7 days.',
    stats: data.kanban_throughput.map(d => ({ label: d.date, value: String(d.completed) })),
  }

  // Token breakdown
  const tokensInput = data.tokens_input ?? 0
  const tokensOutput = data.tokens_output ?? 0
  const tokensTotal = tokensInput + tokensOutput
  const inputPct = tokensTotal > 0 ? (tokensInput / tokensTotal) * 100 : 50
  const tokenInfo: InfoObject = {
    category: 'Tokens', title: 'Token Breakdown', accent: '#f6b73c',
    desc: 'Input vs output tokens used across all sessions in the time window.',
    stats: [
      { label: 'Input tokens', value: fmtNum(tokensInput) },
      { label: 'Output tokens', value: fmtNum(tokensOutput) },
    ],
  }

  // Skill usage
  const maxSkillCount = Math.max(...data.top_skills.map(s => s.count), 1)
  const totalSkillCount = data.top_skills.reduce((s, sk) => s + sk.count, 0)
  const skillsInfo: InfoObject = {
    category: 'Skills', title: 'Skill Usage', accent,
    desc: 'Top skills invoked by agents, ranked by call count.',
    stats: data.top_skills.map(s => ({ label: s.skill, value: String(s.count) })),
  }

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header className="flex items-center justify-between" style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Usage Analytics</div>
          <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>Live · last 7 days</div>
        </div>
        <span className="inline-flex items-center" style={{ gap: 6, fontSize: 12, color: '#c6cad8', background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 20, padding: '5px 12px' }}>
          Live · last 7 days
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#9298ab" strokeWidth={2} aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
        </span>
      </header>
      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '22px 26px 40px' }}>
        <div style={{ maxWidth: 1080, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16, animation: 'hpanelin 0.4s var(--ease-out)' }}>

          {/* KPI tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
            {kpis.map((k) => (
              <button
                key={k.label}
                onClick={() => open(k.info)}
                className="relative overflow-hidden text-left"
                style={{ background: 'var(--s3)', border: '1px solid var(--border)', borderRadius: 13, padding: '16px 17px', cursor: 'pointer', transition: 'transform 0.25s, border-color 0.25s, box-shadow 0.25s' }}
                onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.16)'; e.currentTarget.style.boxShadow = '0 14px 34px rgba(0,0,0,0.45)' }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = 'none' }}
              >
                <span style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 2, background: k.accent }} />
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 26, color: 'var(--text-primary)' }}>{k.value}</div>
                <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088', marginTop: 5 }}>{k.label}</div>
              </button>
            ))}
          </div>

          {/* Activity by Day + Token Breakdown */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.3fr) minmax(0,1fr)', gap: 16 }}>
            <div style={cardBase} onClick={() => open(activityInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
              <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
                <div style={cardLabel}>Activity by Day</div>
                <span style={{ fontSize: 10.5, color: '#2dd4bf', background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.28)', borderRadius: 6, padding: '2px 8px' }}>Peak {peakEntry.date}</span>
              </div>
              <div className="flex items-end" style={{ gap: 5, height: 96 }}>
                {bars.map((d, i) => (
                  <div key={i} style={{ flex: 1, minWidth: 0, height: d.h, borderRadius: '3px 3px 0 0', background: d.bg }} />
                ))}
              </div>
            </div>

            <div style={cardBase} onClick={() => open(tokenInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
              <div style={{ ...cardLabel, marginBottom: 16 }}>Token Breakdown</div>
              <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 26, color: 'var(--text-primary)', marginBottom: 16 }}>{fmtNum(tokensTotal)}</div>
              <div className="flex" style={{ height: 10, borderRadius: 99, overflow: 'hidden', background: 'rgba(255,255,255,0.05)', marginBottom: 14 }}>
                <div style={{ width: `${inputPct}%`, background: 'var(--ac)', borderRadius: '99px 0 0 99px' }} />
                <div style={{ width: `${100 - inputPct}%`, background: '#5aa2f0', borderRadius: '0 99px 99px 0' }} />
              </div>
              <div className="flex flex-wrap" style={{ gap: '8px 14px' }}>
                <span className="inline-flex items-center" style={{ gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: 'var(--ac)' }} />
                  Input <b style={{ color: '#d4d8e4', fontWeight: 600 }}>{fmtNum(tokensInput)}</b>
                </span>
                <span className="inline-flex items-center" style={{ gap: 6, fontSize: 12, color: 'var(--text-muted)' }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: '#5aa2f0' }} />
                  Output <b style={{ color: '#d4d8e4', fontWeight: 600 }}>{fmtNum(tokensOutput)}</b>
                </span>
              </div>
            </div>
          </div>

          {/* Skill usage */}
          <div style={cardBase} onClick={() => open(skillsInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
            <div style={{ ...cardLabel, marginBottom: 14 }}>Skill Usage</div>
            <div className="flex flex-col" style={{ gap: 11 }}>
              {data.top_skills.map((sk) => (
                <div key={sk.skill} className="flex items-center" style={{ gap: 12 }}>
                  <span className="mono flex-none" style={{ width: 140, fontSize: 12, color: '#c6cad8' }}>{sk.skill}</span>
                  <div className="flex-1" style={{ height: 7, borderRadius: 99, background: 'rgba(255,255,255,0.05)', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.round((sk.count / maxSkillCount) * 100)}%`, borderRadius: 99, background: 'linear-gradient(90deg, color-mix(in oklab, var(--ac) 60%, transparent), var(--ac))' }} />
                  </div>
                  <span className="mono flex-none" style={{ width: 40, textAlign: 'right', fontSize: 11.5, color: 'var(--text-muted)' }}>{sk.count}</span>
                  <span className="mono flex-none" style={{ width: 40, textAlign: 'right', fontSize: 11, color: '#565d72' }}>{totalSkillCount > 0 ? `${Math.round((sk.count / totalSkillCount) * 100)}%` : '0%'}</span>
                </div>
              ))}
              {data.top_skills.length === 0 && (
                <div style={{ fontSize: 12, color: '#565d72' }}>No skill data yet</div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}
