/** A single callable command exposed by a skill/plugin. */
export interface SkillCommand {
  name: string
  sig: string
  desc: string
}

/** A skill/plugin the agent can call. Mirrors the prototype's PLUGINS. */
export interface Skill {
  id: string
  name: string
  cat: string
  desc: string
  skills: string[]
  on: boolean
  long: string
  author: string
  version: string
  scope: string
  calls7d: number
  commands: SkillCommand[]
}

export const SKILLS: Skill[] = [
  {
    id: 'obsidian',
    name: 'Obsidian',
    cat: 'Knowledge',
    desc: 'Read, search, and create notes in the Obsidian vault.',
    skills: ['read-note', 'search', 'create-note'],
    on: true,
    long:
      'Gives the agent direct read/write access to the local Obsidian vault. Hermes uses it to recall decisions, pull context from project notes, and write new findings back as linked markdown so memory persists between sessions.',
    author: 'core',
    version: '1.4.0',
    scope: 'workspace vault',
    calls7d: 71,
    commands: [
      { name: 'read-note', sig: 'read-note(path)', desc: 'Return the full markdown body of a single note by vault path.' },
      { name: 'search', sig: 'search(query, limit?)', desc: 'Full-text + tag search across the vault; returns ranked note snippets.' },
      { name: 'create-note', sig: 'create-note(path, body)', desc: 'Create or append a note, auto-linking [[wikilinks]] back to the source.' },
    ],
  },
  {
    id: 'notion',
    name: 'Notion',
    cat: 'Knowledge',
    desc: 'Notion API for creating and managing pages, databases, and blocks.',
    skills: ['pages', 'databases'],
    on: true,
    long:
      'Connects to a Notion workspace over the official API. Used to sync task status into shared databases and draft hand-off pages humans can review without opening Hermes.',
    author: 'core',
    version: '0.9.2',
    scope: 'team workspace',
    calls7d: 38,
    commands: [
      { name: 'pages', sig: 'pages.create / update(id, blocks)', desc: 'Create or patch a page from block content; supports rich text and callouts.' },
      { name: 'databases', sig: 'databases.query(id, filter)', desc: 'Query a database with filters/sorts and map rows into structured records.' },
    ],
  },
  {
    id: 'dogfood',
    name: 'Dogfood QA',
    cat: 'Testing',
    desc: 'Systematic exploratory QA testing of web applications.',
    skills: ['explore', 'report'],
    on: false,
    long:
      'Drives a headless browser to exercise a running web app the way a tester would — clicking through flows, probing edge cases, and capturing repro steps. Disabled by default because runs are slow and consume a worker.',
    author: 'labs',
    version: '0.3.1',
    scope: 'sandbox',
    calls7d: 0,
    commands: [
      { name: 'explore', sig: 'explore(url, goal)', desc: 'Crawl a target app toward a goal, logging every interaction and assertion.' },
      { name: 'report', sig: 'report(runId)', desc: 'Compile findings into a triaged bug report with severity and repro steps.' },
    ],
  },
  {
    id: 'webfetch',
    name: 'Web Fetch',
    cat: 'Web',
    desc: 'Fetch and extract readable content from any URL.',
    skills: ['fetch'],
    on: true,
    long:
      "Fetches a URL server-side and strips it down to clean, readable text — no ads, nav, or scripts. The agent's primary way to ground answers in live external sources.",
    author: 'core',
    version: '2.1.0',
    scope: 'public web',
    calls7d: 142,
    commands: [
      { name: 'fetch', sig: 'fetch(url, format?)', desc: 'Retrieve a page or PDF and return extracted text or structured markdown.' },
    ],
  },
  {
    id: 'gh',
    name: 'GitHub',
    cat: 'Dev',
    desc: 'Browse repos, open PRs, and read issues across GitHub.',
    skills: ['repos', 'prs', 'issues'],
    on: true,
    long:
      'Read/write access to connected GitHub repositories. Hermes inspects code, opens pull requests for fixes, and reconciles issue state against the Kanban board.',
    author: 'core',
    version: '1.7.3',
    scope: '4 repos',
    calls7d: 56,
    commands: [
      { name: 'repos', sig: 'repos.read(path, ref?)', desc: 'Read files, trees, and commit history from a connected repository.' },
      { name: 'prs', sig: 'prs.open(branch, title, body)', desc: 'Open a pull request from a working branch with a generated summary.' },
      { name: 'issues', sig: 'issues.list / comment(repo)', desc: 'List, label, and comment on issues; mirror status to the board.' },
    ],
  },
  {
    id: 'voice-rt',
    name: 'Voice RT',
    cat: 'Audio',
    desc: 'Real-time RVC voice conversion + latency benchmarking.',
    skills: ['convert', 'bench'],
    on: false,
    long:
      'Runs realtime RVC voice conversion and measures end-to-end latency against the project gate. GPU-heavy — keep it off unless a worker with a free GPU is available.',
    author: 'labs',
    version: '0.2.0',
    scope: 'executor',
    calls7d: 0,
    commands: [
      { name: 'convert', sig: 'convert(stream, model)', desc: 'Stream audio through an RVC model and emit converted audio in realtime.' },
      { name: 'bench', sig: 'bench(model, samples)', desc: 'Benchmark conversion latency and report p50/p95 against the gate.' },
    ],
  },
]
