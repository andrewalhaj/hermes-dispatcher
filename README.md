# Hermes Dispatcher

**Mission-control dashboard for orchestrating AI worker agents.**

Hermes Dispatcher is a self-hosted web dashboard that gives you a live, operational view of a [Hermes](https://claude-code.nousresearch.com) agent swarm. It surfaces kanban task state, agent memory, session history, system health, logs, and skills — all in one dark-themed UI designed for a single operator running multiple AI workers in parallel.

![Dashboard](https://img.shields.io/badge/stack-React%20%2B%20Vite%20%2B%20FastAPI-blueviolet) ![Python](https://img.shields.io/badge/python-3.11-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## What it is

Hermes is an AI agent system that runs Claude-based workers on a kanban board. Workers pick up cards, execute tasks (code, research, automation), and push results back to the board. The Dispatcher is the **operator's window** into that system — a real-time dashboard served from the host machine, accessible over Tailscale or Cloudflare Tunnel.

---

## Features

### 🗂 Kanban Board
Live view of the agent task board. Cards move through `todo → ready → running → blocked → done`. A **Ready for Review** virtual column surfaces `blocked` tasks flagged for human approval (the review-required gate used by coding workers before merge). Filter by assignee, status, and tenant.

### 💬 Chat
Full conversation interface with the Hermes agent. Supports multi-turn sessions, streaming responses, plan blocks (structured agent reasoning rendered inline), and model/reasoning-effort selection. Sessions are filterable to the Telegram source — cron and subagent sessions don't pollute the history. Styled with the ruixen-mono-chat design language: avatar + name + timestamp rows, read-status ticks, reaction pills, and a pill composer.

### 📊 Mission Overview
Top-level operational summary:
- **Hero tile** — GlowHorizon ambient background, live KPI chips (active agents, tasks run, sessions)
- **Stat grid** — key metrics with sparkline history
- **Agent breakdown** — per-agent task counts and status with color coding
- **Activity heatmap** — session volume over time with time-frame selector (Day / Week / Month)
- **System Monitor** — live CPU, GPU, VRAM, and network for both Mac Mini (Intel UHD 630) and Mac Studio (Apple Silicon M-series), polled every 3s with 60fps animated arc gauges and per-metric accent colors
- **Agent Swarm canvas** — particle simulation showing live agent activity, color-coded per worker

### 🖥 System Monitor
Dual-machine monitoring (Mac Mini + Mac Studio over Tailscale SSH):

| Metric | Mac Mini | Mac Studio |
|--------|----------|------------|
| CPU % | `psutil` | `psutil` (SSH) |
| RAM | `psutil` | `psutil` (SSH) |
| GPU % | `/proc/*/fdinfo` drm-engine-render delta | `ioreg IOAccelerator` |
| VRAM % | `i915_gem_objects` stolen memory | `ioreg` in-use system memory |
| Network MB/s | `psutil` | `psutil` (SSH) |

Machine selection persists across reloads. Tile is collapsible with a hide/show toggle.

### 🧠 Memory Editor
View and edit Hermes memory stores directly from the dashboard: `MEMORY.md`, `USER.md`, `SOUL.md`, and `AGENTS.md`. Per-profile support — switch between default and named profiles. Changes write through to the live agent context.

### 🔍 Insights
Token usage, session counts, and activity analytics. Skill usage tracking with a full info panel per skill. Agent-level breakdowns. Heatmap with Day / Week / Month time-frame selector.

### 📋 Sessions
Browse and replay past agent sessions. Click any session to load the full message thread. Filter by source platform (Telegram, local, cron).

### 🛠 Skills
Browse all installed Hermes skills. Toggle skills on/off per platform. Skills show their trigger description and category. Changes take effect on the next agent session.

### 👥 Agents
Live agent roster — which profiles are active, their task history, memory footprint (RSS MB), and color-coded status. Capitalized display names. No stale/deleted profiles.

### 📁 Workspace
Browse the active kanban task workspace — file tree and contents for the current worker's scratch directory.

### 📝 Logs
Tail live logs from the Hermes gateway, dashboard server, and system journal. Auto-scroll with pause-on-hover.

### ⚙️ Settings
Persist dashboard preferences: theme, accent color, agent name, workspace path, and dashboard toggles. All controls auto-save on change and survive full page reloads. Backend is the source of truth; localStorage mirrors for instant load.

---

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Framer Motion |
| Backend | FastAPI (Python 3.11), uvicorn |
| Data | SQLite (kanban + sessions via Hermes), `psutil`, SSH probes |
| Auth | Session cookie (`hd_session`), bcrypt password hash |
| Fonts | Space Grotesk |
| Hosting | Self-hosted on Mac Mini, exposed via Cloudflare Tunnel |

---

## Architecture

```
Browser (Mac Studio / any Tailscale client)
    │
    ├─ hermes.andrewskingdom.com  ──►  Cloudflare Tunnel
    │                                        │
    └─ 100.113.100.81:8787  ────────────────►│
                                             ▼
                                    Mac Mini (host)
                                    ┌─────────────────────┐
                                    │  uvicorn :8787       │
                                    │  server.py           │
                                    │  ├─ /api/kanban      │
                                    │  ├─ /api/system      │
                                    │  ├─ /api/chat        │
                                    │  ├─ /api/sessions    │
                                    │  ├─ /api/memory      │
                                    │  ├─ /api/skills      │
                                    │  ├─ /api/insights    │
                                    │  ├─ /api/agents      │
                                    │  └─ /api/logs        │
                                    │                      │
                                    │  Reads: kanban.db    │
                                    │         ~/.hermes/   │
                                    │                      │
                                    │  SSH probe ──────────┼──► Mac Studio (100.93.2.43)
                                    └─────────────────────┘    GPU/CPU/RAM metrics
```

The kanban board (`~/.hermes/kanban.db`) is a shared SQLite DB written by the Hermes dispatcher process and read by the dashboard. Workers run on the Mac Mini and SSH into remote hosts for tasks — they do not run Claude on remote machines.

---

## Running locally

```bash
# Backend
cd /root/hermes-dispatcher
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8787 --reload

# Frontend (dev)
cd app
npm install
npm run dev

# Frontend (production build)
npm run build
# served automatically by uvicorn from app/dist/
```

Password hash is stored at `.dashboard_passwd_hash` (bcrypt). Set via:
```bash
python3 -c "import hashlib; print(hashlib.sha256(b'yourpassword').hexdigest())" > .dashboard_passwd_hash
```

---

## Deployment

Runs as a systemd service on Mac Mini:

```ini
# /etc/systemd/system/hermes-dashboard.service.d/dispatcher-override.conf
[Service]
ExecStart=/root/hermes-dispatcher/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8787
WorkingDirectory=/root/hermes-dispatcher
Environment=HERMES_HOME=/root/.hermes
Restart=always
RestartSec=3
```

Exposed externally via Cloudflare Tunnel at `hermes.andrewskingdom.com`.

---

## License

MIT
