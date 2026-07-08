export interface Command {
  cmd: string
  description: string
}

export const COMMANDS: Command[] = [
  { cmd: '/help', description: 'Show available commands' },
  { cmd: '/clear', description: 'Clear the current conversation' },
  { cmd: '/new', description: 'Start a new conversation' },
  { cmd: '/model', description: 'Switch model  e.g. /model claude-opus-4-8' },
  { cmd: '/compress', description: 'Compress context to save tokens' },
  { cmd: '/usage', description: 'Show token usage for this session' },
  { cmd: '/linear search', description: 'Search Linear issues  e.g. /linear search memory leak' },
  { cmd: '/linear create', description: 'Create a Linear issue  e.g. /linear create Fix login p:1' },
]
