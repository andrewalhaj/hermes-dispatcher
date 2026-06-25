# Panels — Layout, Elements, Current State

*All panels are full-screen (take the full viewport minus the sidebar). Only one is active at a time. Switching is via `switchPanel(name)` triggered by the nav rail.*

---

## Overview Panel (`panel === 'overview'`)

**Nav label:** Overview (top of sidebar, under WORKSPACE)

### Sections (top to bottom)
1. **Hero / Mission Overview** — full-width starfield canvas banner
   - "MISSION OVERVIEW" label (gold, small caps)
   - Greeting: "Good evening, operator" (32px bold white)
   - Date: "Friday, June 19" (muted)
   - Status pills row: Dispatcher live · N running · N ready · N blocked
   - KPI counters (top-right): TASKS RUN / ACTIVE SESSIONS / DAY STREAK (gold numbers)

2. **Metric cards row** (4 columns)
   - Tasks Run (gold accent)
   - Active Sessions (teal accent)
   - Tenants (blue accent)
   - Memory Items (purple accent)

3. **Middle row** (2 columns)
   - Agent Breakdown donut chart (left)
   - Agent Activity Heatmap — 24h grid (right)

4. **Bottom row** (2 columns, partially visible)
   - System Monitor (CPU/GPU/RAM bars, host selector)
   - Agent Swarm canvas (particle field)

### Data sources
- Status pills: `window.__RD_KANBAN__` (live board counts)
- KPI numbers: `window.__RD_INS__` (insights stats)
- Donut chart: kanban task_runs grouped by profile
- Heatmap: 14-day message activity from state.db
- System monitor: `/api/insights` (psutil-backed)
- Swarm: `window.__RD_SWARM__` → `ensureSwarm()` canvas

---

## Chat Panel (`panel === 'chat'`)

**Nav label:** Chat

### Current state
- **FAKE streaming** — agent runs as subprocess, full response buffered, then cosmetically re-chunked at 40 chars/30ms
- Chat sends to the shared Hermes agent (same session as Telegram)
- Profile selector: Hermes / HAJarvis / Executor (maps to `--profile` flag)
- Agent list rendered from `window.__RD_CHAT__.agents`
- Message history seeded from last webui session in state.db

### Layout
- Left: agent/session sidebar (profile avatars, status)
- Main: message thread
- Bottom: composer input + send button

### Planned upgrades
- Real token-streaming (Phase 1 of feature-port plan)
- Cancel button
- Tool call cards
- Session search/pin/archive

---

## Kanban Panel (`panel === 'kanban'`)

**Nav label:** Kanban (under WORKSPACE)

### Current state — FULLY WIRED, real-time SSE
The Kanban panel is the most complete panel. It has:
- Live board via SSE at `/api/kanban/events/stream` (polls kanban.db fingerprint ~2s)
- Full CRUD: create, edit, move, comment, dispatch tasks
- Columns: triage → todo → ready → running → blocked → done
- Filters: assignee, tenant, include-archived
- Task detail view (click a card) with timeline, comments, runs, body markdown
- Multi-board support
- Worker list sidebar

### Layout
- Top: board name + filter controls
- Main: kanban column swimlanes (horizontal scroll)
- Each card: title, assignee badge, status chip, age indicator, quick-action buttons
- Click card → detail panel slides in from right

### Column styling
Each column has a colored header dot matching the status color:
- Triage: gray (#6a7088)
- Todo: blue (#5aa2f0)
- Ready: gold (#f6b73c)
- Running: teal (#2dd4bf), pulse animation
- Blocked: red (#fb6f6f)
- Done: green (#4ade80)

---

## Memory Panel (`panel === 'memory'`)

**Nav label:** Memory (under SYSTEM)

### Current state — WIRED
Shows content from `window.__RD_MEMORY__`:
- Notes tab: MEMORY.md §-entries
- Profile tab: USER.md entries + Honcho peer card
- Soul tab: SOUL.md sections
- Context tab: AGENTS.md + Honcho user model observations

### Layout
- Sub-tabs across top (Notes / Profile / Soul / Context)
- Each tab: scrollable list of entries
- Entry card: primary text (bold) + secondary text (muted)

### Memory Galaxy (`panel === 'memory'` sub-view)
Toggle button switches to the 3D Galaxy view:
- Canvas fills panel
- 622 nodes across 7 tiers (see galaxy tier colors in design-system.md)
- Drag to orbit (3D rotation), scroll to zoom
- Click node → detail card (title, body, importance, age)
- Tier legend chips across top
- Search filter input
- Synapse burst animation (cluster-area flicker)

---

## Insights Panel (`panel === 'insights'`)

**Nav label:** Insights (under SYSTEM)

### Current state — PARTIALLY WIRED
- Main stats (sessions, messages, tokens, cost) from `window.__RD_INS__`
- Model breakdown (top 3 by session count) from state.db
- Skills usage section from skill usage JSON
- Heatmap: 14-day message activity
- System health: CPU/RAM/disk from `/api/insights` psutil data

### Known gap
Falls back to hardcoded demo numbers if `__RD_INS__` is empty or the period has no data.

---

## Logs Panel (`panel === 'logs'`)

**Nav label:** Logs (under SYSTEM)

### Current state — WIRED
- Pulls from `/api/logs`
- File selector: `hermes.log`, `gateway.log`, etc.
- Tail selector: 100 / 500 / 1000 lines
- Severity filter: all / INFO / WARNING / ERROR
- Auto-refresh toggle (5s interval)
- Copy all button

### Layout
- Top: file selector + tail + filter + copy + refresh
- Main: monospace log lines, color-coded by severity
  - INFO: muted (#8c92a6)
  - WARNING: gold (#f6b73c)
  - ERROR: red (#fb6f6f)

---

## Agents Panel (`panel === 'agents'`)

**Nav label:** Agents (under WORKSPACE)

### Current state — WIRED (profiles only)
Shows agent profiles from `window.__RD_SWARM__.profiles`:
- Profile avatar (initials + color)
- Name, role label
- Status dot (running=teal pulse, online=green, idle=gray)
- Task count from kanban task_runs

---

## Skills Panel

**Nav label:** Skills (under SYSTEM)

### Current state — READ-ONLY list
- From `/api/skills` → name + description only
- Categories from frontmatter
- Search filter
- No expand, no edit, no create

### Planned upgrade (Phase 4)
- Full SKILL.md content viewer
- Create / edit / delete

---

## Settings Panel (`panel === 'settings'`)

**Nav label:** Settings (under SYSTEM)

### Current state
Persists to `~/.hermes/webui_settings.json` only. Does NOT modify `~/.hermes/config.yaml` (write-gated). Settings are cosmetic/UI-only:
- Model selector (display only)
- Theme (light/dark toggle, currently always dark)
- Default workspace path
- Auth password change

---

## Panels not yet built (planned)

See `04-feature-gaps.md` for full detail. Short list:
- Workspace file browser (Phase 2)
- Cron/Tasks management (Phase 3)
- Session management improvements (Phase 5)
- Knowledge base panel
- Terminal/PTY panel
