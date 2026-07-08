import { useEffect, useState } from 'react'

export interface LinearIssues {
  open: number
  urgent: number
  stale: number
  error: string | null
  cached: boolean
  updated_at: number
}

const EMPTY: LinearIssues = {
  open: 0,
  urgent: 0,
  stale: 0,
  error: null,
  cached: false,
  updated_at: 0,
}

/**
 * Polls /api/linear/issues every 5 minutes for live Linear issue counts.
 * The backend caches upstream for 5 min, so this cadence never rate-limits
 * Linear. Keeps the last good snapshot on transient fetch errors.
 */
export function useLinearIssues(): { data: LinearIssues; loading: boolean } {
  const [data, setData] = useState<LinearIssues>(EMPTY)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function fetchData() {
      try {
        const res = await fetch('/api/linear/issues', { credentials: 'include' })
        if (!res.ok) return
        const json = (await res.json()) as LinearIssues
        if (!cancelled) setData(json)
      } catch {
        // keep last good data on error
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchData()
    const id = setInterval(fetchData, 5 * 60_000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return { data, loading }
}
