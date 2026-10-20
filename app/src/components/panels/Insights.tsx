import React, { useState, useEffect } from 'react'
import { lsGet, lsSet } from '../../utils/localStorage'
import { ACCENT } from '../../data/agents'
import type { InfoObject } from '../../data/info'
import { useInfo } from '../TileInfoDrawer'
import '../../styles/phase3.css'

interface InsightsAPI {
  days: number
  tasks_started: number
  success_rate: number
  avg_latency_s: number
  by_profile: Array<{ profile: string; completed: number; running: number; success_rate: number }>
  sessions: number
  messages: number
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
  background: 'var(--s3)', border: '1px solid var(--tile-border)', borderRadius: 14, padding: 18,
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

const RANGES = [{ days: 1, label: 'Last day', short: 'last 24h' }, { days: 3, label: 'Last 3 days', short: 'last 3 days' }, { days: 7, label: 'Last 7 days', short: 'last 7 days' }]
const RANGE_KEY = 'insights.days'

function fmtNum(n: number): string {
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

export default function Insights({ accent = ACCENT }: InsightsProps) {
  const [data, setData] = useState<InsightsAPI | null>(null)
  const [error, setError] = useState(false)
  const [days, setDays] = useState(() => { const d = Number(lsGet(RANGE_KEY, '7')); return RANGES.some(x => x.days === d) ? d : 7 })
  const { openInfo } = useInfo()
  const open = openInfo

  useEffect(() => {
    let cancelled = false
    async function fetchData() {
      try {
        const res = await fetch(`/api/insights?days=${days}`)
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
  }, [days])

  if (!data) {
    return (
      <div className="flex flex-1 items-center justify-center" style={{ color: error ? '#f6b73c' : '#6a7088', fontSize: 14 }}>
        {error ? 'Could not load insights' : 'Loading analytics…'}
      </div>
    )
  }

  const range = RANGES.find(x => x.days === days) ?? RANGES[2]
  const win = range.short

  // KPI tiles
  const kpis: Array<{ label: string; value: string; accent: string; info: InfoObject }> = [
    {
      label: 'Tasks started', value: String(data.tasks_started), accent,
      info: { category: 'Tasks', title: 'Tasks started', accent, value: String(data.tasks_started), desc: `Kanban tasks whose started_at falls in the ${win}.`, stats: [{ label: 'Success Rate', value: `${data.success_rate}%` }] },
    },
    {
      label: 'Sessions opened', value: String(data.sessions), accent: '#5aa2f0',
      info: { category: 'Sessions', title: 'Sessions opened', accent: '#5aa2f0', value: String(data.sessions), desc: `Chat and worker sessions started in the ${win}, across all profiles.`, stats: [{ label: 'Messages', value: fmtNum(data.messages) }] },
    },
    {
      label: 'Messages (all profiles)', value: fmtNum(data.messages), accent: '#2dd4bf',
      info: { category: 'Messages', title: 'Messages (all profiles)', accent: '#2dd4bf', value: fmtNum(data.messages), desc: `Messages stored in the ${win} across the default and every profile's state.db.`, stats: [] },
    },
    {
      label: 'Success Rate', value: `${data.success_rate}%`, accent: '#9b8cff',
      info: { category: 'Quality', title: 'Success Rate', accent: '#9b8cff', value: `${data.success_rate}%`, desc: `Completed / terminal task runs that ended in the ${win}.`, stats: [{ label: 'Tasks started', value: String(data.tasks_started) }] },
    },
    {
      label: 'Avg Task Duration', value: `${data.avg_latency_s}s`, accent: '#f6b73c',
      info: { category: 'Duration', title: 'Avg Task Duration', accent: '#f6b73c', value: `${data.avg_latency_s}s`, desc: `Mean of (ended_at - started_at) over completed task runs that ended in the ${win}.`, stats: [] },
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
    category: 'Activity', title: `Activity by ${days === 1 ? 'Hour' : 'Day'}`, accent,
    desc: `Kanban task runs completed per ${days === 1 ? 'hour' : 'day'} over the ${win}.`,
    stats: data.kanban_throughput.map(d => ({ label: d.date, value: String(d.completed) })),
  }

  // Token breakdown
  const tokensInput = data.tokens_input ?? 0
  const tokensOutput = data.tokens_output ?? 0
  const tokensTotal = tokensInput + tokensOutput
  const inputPct = tokensTotal > 0 ? (tokensInput / tokensTotal) * 100 : 50
  const tokenInfo: InfoObject = {
    category: 'Tokens', title: 'Token Breakdown', accent: '#f6b73c',
    desc: `Input vs output tokens, summed over sessions started in the ${win} (all profiles).`,
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
    desc: `Top skills loaded via skill_view in the ${win} (all profiles), ranked by call count.`,
    stats: data.top_skills.map(s => ({ label: s.skill, value: String(s.count) })),
  }

  return (
    <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
      <header className="flex items-center justify-between" style={{ flex: 'none', padding: '16px 26px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
        <div>
          <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, fontSize: 20, color: 'var(--text-primary)' }}>Usage Analytics</div>
          <div style={{ fontSize: 12, color: '#6a7088', marginTop: 2 }}>Live · {win}</div>
        </div>
        <div role="group" aria-label="Time range" className="inline-flex" style={{ gap: 2, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.12)', borderRadius: 20, padding: 2 }}>
          {RANGES.map(x => (
            <button
              key={x.days}
              aria-pressed={x.days === days}
              onClick={() => { lsSet(RANGE_KEY, String(x.days)); setData(null); setDays(x.days) }}
              style={{ fontSize: 12, padding: '4px 12px', borderRadius: 18, cursor: 'pointer', border: 'none', color: x.days === days ? 'var(--text-primary)' : '#9298ab', background: x.days === days ? 'rgba(255,255,255,0.12)' : 'transparent' }}
            >{x.label}</button>
          ))}
        </div>
      </header>
      <div className="flex-1 overflow-y-auto" style={{ minHeight: 0, padding: '22px 26px 40px' }}>
        <div style={{ maxWidth: 1080, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16, animation: 'hpanelin 0.4s var(--ease-out)' }}>

          {/* KPI tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12 }}>
            {kpis.map((k, i) => (
              <button
                key={k.label}
                onClick={() => open(k.info)}
                className="relative overflow-hidden text-left"
                style={{ background: 'var(--s3)', border: '1px solid var(--tile-border)', borderRadius: 13, padding: '16px 17px', cursor: 'pointer', transition: 'transform 0.25s, border-color 0.25s, box-shadow 0.25s', animation: 'hcellin 0.45s ease backwards', animationDelay: `${i * 0.07}s` }}
                onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.borderColor = 'var(--tile-border-hover)'; e.currentTarget.style.boxShadow = '0 14px 34px rgba(0,0,0,0.45)' }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.borderColor = 'var(--tile-border)'; e.currentTarget.style.boxShadow = 'none' }}
              >
                <span style={{ position: 'absolute', left: 0, right: 0, top: 0, height: 2, background: k.accent }} />
                <div style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: 26, color: 'var(--text-primary)' }}>{k.value}</div>
                <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: '#6a7088', marginTop: 5 }}>{k.label}</div>
              </button>
            ))}
          </div>

          {/* Activity by Day + Token Breakdown */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            <div style={{ ...cardBase, animation: 'hcellin 0.45s ease backwards', animationDelay: '0.35s' }} onClick={() => open(activityInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
              <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
                <div style={cardLabel}>Activity by {days === 1 ? 'Hour' : 'Day'}</div>
                <span style={{ fontSize: 10.5, color: '#2dd4bf', background: 'rgba(45,212,191,0.1)', border: '1px solid rgba(45,212,191,0.28)', borderRadius: 6, padding: '2px 8px' }}>Peak {peakEntry.date}</span>
              </div>
              <div className="flex" style={{ gap: 8 }}>
                {/* Y-axis scale */}
                <div className="flex flex-col flex-none" style={{ justifyContent: 'space-between', height: 96, fontSize: 9, color: '#565d72', textAlign: 'right', width: 18, fontVariantNumeric: 'tabular-nums' }}>
                  <span>{maxCompleted}</span>
                  <span>{Math.round(maxCompleted / 2)}</span>
                  <span>0</span>
                </div>
                {/* Bars + X-axis labels */}
                <div className="flex flex-1" style={{ gap: 5, minWidth: 0 }}>
                  {bars.map((d, i) => (
                    <div key={i} className="flex flex-col items-center" style={{ flex: 1, minWidth: 0 }}>
                      <div className="flex items-end justify-center" style={{ width: '100%', height: 96 }}>
                        <div style={{ width: '100%', height: d.h, borderRadius: '3px 3px 0 0', background: d.bg }} />
                      </div>
                      <span style={{ marginTop: 6, fontSize: 9.5, color: '#6a7088', letterSpacing: '0.02em', visibility: days === 1 && i % 4 ? 'hidden' : 'visible' }}>{d.date}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div style={{ ...cardBase, animation: 'hcellin 0.45s ease backwards', animationDelay: '0.42s' }} onClick={() => open(tokenInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
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
          <div style={{ ...cardBase, animation: 'hcellin 0.45s ease backwards', animationDelay: '0.49s' }} onClick={() => open(skillsInfo)} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
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
