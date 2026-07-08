import type { AgentRow, ChatAgent } from './types'

export const ACCENT = '#f6b73c'

/** Worker fleet — mirrors the prototype's CHAT_AGENTS. */
export const CHAT_AGENTS: ChatAgent[] = [
  { key: 'hermes', name: 'Hermes', role: 'Coordinator', platform: 'Dispatcher', icon: '⚕', color: ACCENT, status: 'online' },
  { key: 'executor', name: 'executor', role: 'GPU bench', platform: 'voice-rt', icon: '◆', color: '#2dd4bf', status: 'online', running: true },
  { key: 'coder-c', name: 'coder-c', role: 'ETL worker', platform: 'atlas-crm', icon: '▣', color: '#5aa2f0', status: 'online', running: true },
  { key: 'coder-d', name: 'coder-d', role: 'Content', platform: 'dm-voice-board', icon: '❖', color: '#9b8cff', status: 'idle' },
  { key: 'coder-e', name: 'coder-e', role: 'Infra', platform: 'internal', icon: '⬢', color: '#4ade80', status: 'idle' },
]

/** Resolve each agent's live-status pill for the left-rail AGENTS list. */
export function agentRows(accent = ACCENT): AgentRow[] {
  return CHAT_AGENTS.map((a) => {
    const st = a.running ? 'run' : a.status
    return {
      key: a.key,
      name: a.name,
      dot: st === 'run' ? accent : st === 'online' ? '#4ade80' : '#565d72',
      dotGlow: st === 'idle' ? 'none' : `0 0 8px ${st === 'run' ? accent : '#4ade80'}`,
      badge: st === 'run' ? 'RUN' : st === 'online' ? 'LIVE' : 'IDLE',
      badgeColor: st === 'run' ? accent : st === 'online' ? '#4ade80' : '#818799',
      badgeBg:
        st === 'run'
          ? `color-mix(in oklab, ${accent} 12%, transparent)`
          : st === 'online'
            ? 'rgba(74,222,128,0.1)'
            : 'rgba(255,255,255,0.05)',
    }
  })
}
