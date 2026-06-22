import { useEffect, useState } from 'react'

export interface KanbanSummary {
  running: number
  blocked: number
  done_today: number
  ready: number
}

export interface OverviewSystem {
  cpu_pct: number
  mem_pct: number
  disk_pct: number
}

export interface RecentActivity {
  id: string
  title: string
  assignee: string | null
  completed_at: number
}

export interface SparklinePoint {
  hour: number
  count: number
}

export interface AgentBreakdownItem {
  name: string
  count: number
}

export interface AgentActivityItem {
  name: string
  hours: number[]
}

export interface AgentMemoryItem {
  name: string
  rss_mb: number
}

export interface OverviewApiData {
  kanban_summary: KanbanSummary
  active_agents: number
  system: OverviewSystem
  recent_activity: RecentActivity[]
  sparkline: SparklinePoint[]
  total_tasks: number
  agent_breakdown: AgentBreakdownItem[]
  agent_activity: AgentActivityItem[]
  agent_memory: AgentMemoryItem[]
}

const EMPTY: OverviewApiData = {
  kanban_summary: { running: 0, blocked: 0, done_today: 0, ready: 0 },
  active_agents: 0,
  system: { cpu_pct: 0, mem_pct: 0, disk_pct: 0 },
  recent_activity: [],
  sparkline: Array.from({ length: 24 }, (_, i) => ({ hour: i, count: 0 })),
  total_tasks: 0,
  agent_breakdown: [],
  agent_activity: [],
  agent_memory: [],
}

export function useOverviewData(): OverviewApiData {
  const [data, setData] = useState<OverviewApiData>(EMPTY)

  useEffect(() => {
    let cancelled = false

    async function fetchData() {
      try {
        const res = await fetch('/api/overview')
        if (!res.ok) return
        const json = (await res.json()) as OverviewApiData
        if (!cancelled) setData(json)
      } catch {
        // keep last good data on error
      }
    }

    fetchData()
    const id = setInterval(fetchData, 10_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return data
}
