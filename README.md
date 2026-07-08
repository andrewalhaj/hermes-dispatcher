# Hermes Dispatcher

**Mission-control dashboard, webhook fleet, and API backend for orchestrating AI worker agents.**

Hermes Dispatcher is a self-hosted FastAPI server that provides a live operational dashboard over a Hermes agent swarm. It combines a React SPA dashboard with a suite of inbound webhook receivers that translate events from development tools into agent actions — creating issues, updating Kanban boards, storing facts, and notifying Telegram.

---

## Features

| Area | Capabilities |
|---|---|
| **Dashboard** | Kanban board with card detail drawer · Chat (streaming, multi-turn, model selection) · Overview (KPIs, agent breakdown, activity heatmap, system monitor) · Memory editor (MEMORY.md, USER.md, AGENTS.md, SOUL.md) · Insights (token usage, analytics) · Session browser/replay · Skill browser (100+ skills, toggle per platform) · Live log tail · Cron output viewer · Linear/Sentry feeds · Settings (theme, accent, prefs) |
| **Webhook integrations** | GitHub (push/PR/issue/review) · Sentry (error alerts → Linear issue) · Linear (issue/comment events → Kanban + Telegram) · Figma (file/comment events) · Notion (page updates + poll sync) · Knowledge store (Supabase INSERT trigger) · Kanban status sync |
| **Autonomous intake** | Sentry error → Linear issue (deduped by Sentry ID) → Kanban card → Telegram notify. Priority-mapped between Linear urgency and Kanban scores. |
| **Data stores** | Supabase pgvector (primary memory — semantic search) · Neo4j (code knowledge graph) · SQLite (Kanban + sessions) · Local markdown (MEMORY.md pointer layer) |

---

## Architecture

```
                     MM01 (Hermes Host)
                         │
  Browser ───────────────┤ uvicorn :8787 (hermes-dispatcher)
  (Tailscale/CF)         │ ├─ /api/{kanban,chat,system,memory,...}
                         │ ├─ /api/hooks/{github,sentry,linear,figma,
                         │ │              notion,knowledge,kanban}
                         │ └─ /app/dist/ (React SPA)
                         │
                         │ hermes-gateway ── Telegram / Discord
                         │ Neo4j (Docker) · Firecrawl · Cloudflare Tunnel
                         │
                         ├──────────────── Tailscale ────────────────┐
                         ▼                                           ▼
                    MS01 (inference node)                 External SaaS
                    Ollama: qwen3-embed,                    Supabase
                    qwen2.5-32b                             Neo4j Aura
                                                            Linear
                                                            Sentry
                                                            GitHub
```

**Hosts:** MM01 (Hermes host — agent gateway, dispatcher, dashboard) · MS01 (inference node — Ollama, GPU workloads).

---

## Quick Start

```bash
# Backend
cd hermes-dispatcher
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create a password hash (required)
python3 -c "import bcrypt; open('.dashboard_passwd_hash','wb').write(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt(rounds=12)))"

# Start
bash start-server.sh
# → Serves dashboard at http://<host>:8787
```

The dashboard SPA is pre-built in `app/dist/` and served automatically by uvicorn. For frontend development:

```bash
cd app
npm install
npm run dev
```

---

## API Surface

| Router | Prefix | Purpose |
|---|---|---|
| `auth` | `/api/login`, `/api/logout`, `/api/session` | Session cookie auth (bcrypt) |
| `kanban` | `/api/kanban` | Kanban board CRUD |
| `chat` | `/api/chat/*` | Agent chat + SSE streaming |
| `sessions` | `/api/sessions` | Past session browser |
| `memory` | `/api/memory` | Memory editor |
| `skills` | `/api/skills` | Skill browser + toggle |
| `agents` | `/api/agents` | Live agent roster |
| `overview` | `/api/overview` | Dashboard stats |
| `insights` | `/api/insights` | Token usage + analytics |
| `system` | `/api/system` | CPU/GPU/RAM/network metrics |
| `logs` | `/api/logs` | Live log tail (SSE) |
| `settings` | `/api/settings` | Dashboard preferences |
| `search` | `/api/search` | Cross-panel search |
| `cron` | `/api/cron` | Cron job output |
| `hooks` | `/api/hooks/*` | Inbound webhook receivers |
| `sentry` | `/api/sentry/messages` | Sentry alert feed |
| `linear` | `/api/linear/*` | Linear issue views |
| `notify` | `/api/notify` | Internal Telegram notification |

All routes serve under `/api`. Webhooks are at `/api/hooks/{github,sentry,linear,figma,notion,knowledge,kanban}`.

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `HERMES_DISPATCHER_PORT` | `8787` | Primary bind port |
| `HERMES_DISPATCHER_BIND_RETRIES` | `3` | Retries on EADDRINUSE |
| `HERMES_DISPATCHER_BIND_BACKOFF` | `2.0` | Seconds between retries |
| `HERMES_DISPATCHER_FALLBACK_PORTS` | — | Comma-separated fallback ports |
| `DASHBOARD_CORS_ORIGINS` | Tailscale + CF domains | Override CORS allowlist |
| `HERMES_HOME` | `~/.hermes` | Hermes data root |
| `OLLAMA_HOST` | — | MS01 Ollama endpoint (for embeddings) |

Required secrets stored in `.env` (git-ignored): `LINEAR_API_KEY`, `SENTRY_*`, `NEO4J_*`, `SUPABASE_*`, `GITHUB_WEBHOOK_SECRET`, etc.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Framer Motion |
| Backend | FastAPI (Python 3.11), uvicorn |
| Data | SQLite, Supabase pgvector, Neo4j (code graph) |
| Auth | Session cookie (`hd_session`), bcrypt (rounds=12) |
| Hosting | Self-hosted on Linux x86_64 |
