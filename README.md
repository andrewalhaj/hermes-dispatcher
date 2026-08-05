# Hermes

A self-hosted AI agent platform. Persistent memory, multi-agent task orchestration, and deep integrations with the tools and services Andrew uses daily. Runs on a 2018 Intel Mac Mini under the desk, reaches out to a Mac Studio for GPU inference and two VPS hosts for Home Assistant and Mealio.

**Profiles:** `default` (orchestrator) · `ha-bot` (Home Assistant) · `executor` · `coder` / `coder-b` / `coder-c` / `coder-d` (swarm workers)

## What it does

### Persistent Memory

Hermes remembers across sessions. Two-tier memory system:

- **Hot memory (`MEMORY.md`, ≤3000 chars):** Facts that fire every turn — behavioral preferences, hard constraints, active pointers. Injected directly into the system prompt.
- **Cold store (Supabase pgvector):** Everything else. Semantic retrieval via B-full auto-RAG — every message gets searched against the cold store at ≥0.80 relevance. Facts that clear the probe get trimmed from hot memory.

Offload pipeline: `offload_probe.py` → TRIM-SAFE classification → `session-end-offload.py` stores to Supabase → trim from MEMORY.md. Session distillation (`session_distill.py`) extracts decisions and outcomes from completed conversations into searchable digests.

### Multi-Agent Task Orchestration

SQLite-backed Kanban board with swarm dispatch. The orchestrator (`default` profile) breaks work into tasks, assigns them to specialist profiles, and the dispatcher spawns workers. Four coder profiles round-robin heavy implementation work. Home Assistant work routes to `ha-bot`.

- **Kanban board:** Tasks flow `triage → todo → ready → running → done`. Blocked tasks park with a reason. Parents fan in; children auto-promote when dependencies resolve.
- **Delegation:** `delegate_task` fans out parallel subtasks within a session. Bounded by depth and concurrency limits.
- **Patches:** Runtime monkey-patches in `patches/` inject enforcement checkpoints (write gate, delegation nudge, domain ownership, skill review) into every session.

### Knowledge Graph (Neo4j)

Supabase pgvector handles semantic search; Neo4j AuraDB handles structured relationships. Webhooks mirror facts from Supabase into Neo4j, where they become graph nodes with edges like `LEARNED_IN`, `SUPERSEDES`, and `RELATED_TO`. Enables traversal queries the vector store can't answer.

### Integrations

Webhook fleet connects Hermes to external services, all routed through `hermes-dispatcher`:

| Service | Purpose |
|---|---|
| **Sentry** | Error monitoring — crash reports surface as kanban cards |
| **Linear** | Issue tracking — bidirectional sync with kanban board |
| **GitHub** | PR review, repo management, code search |
| **Notion** | Documentation, notes, databases |
| **Figma** | Design file access, component inspection |

### Delivery

Hermes talks to Andrew through three channels, all wired through the gateway:

- **Telegram** (primary) — text, rich markdown, media attachments
- **Discord** — secondary channel, cron job delivery
- **WebUI** — React dashboard with session browser, kanban view, memory inspector

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Mac Mini (100.113.100.81)                │
│                    Intel i7-8700B · 15GB · Ubuntu 24.04     │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌───────────┐ │
│  │ Gateway  │  │  Cron    │  │ Dispatcher│  │  WebUI    │ │
│  │ FastAPI  │  │Scheduler │  │ Webhooks  │  │  React    │ │
│  │ :8842    │  │          │  │  :8787    │  │           │ │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘  └───────────┘ │
│       │              │              │                        │
│  ┌────┴──────────────┴──────────────┴────────────────────┐ │
│  │                    Agent Runtime                       │ │
│  │  ┌─────────┐  ┌──────────┐  ┌────────────────────┐    │ │
│  │  │ Skills  │  │ Patches  │  │  Memory Pipeline   │    │ │
│  │  │ 150+    │  │ Write    │  │  Hot → Probe →     │    │ │
│  │  │ skills  │  │ Gate     │  │  Cold (Supabase)   │    │ │
│  │  └─────────┘  └──────────┘  └────────────────────┘    │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  State & Storage                                     │  │
│  │  state.db (SQLite)   ·   Kanban DB (SQLite)          │  │
│  │  MEMORY.md + USER.md ·   references/                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         │ Tailscale          │ Tailscale          │ Internet
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Mac Studio     │  │  HIL-1 VPS      │  │  Cloud Services  │
│   M2 Max · 64GB  │  │  4GB Hetzner    │  │                 │
│                  │  │                  │  │  Supabase       │
│  Ollama :11434   │  │  Mealio :3015    │  │  Neo4j AuraDB   │
│  qwen2.5:72b    │  │  (Next.js app)   │  │  GitHub         │
│  qwen2.5:32b    │  │                  │  │  Linear         │
│  qwen2.5vl:7b   │  │                  │  │  Sentry         │
└─────────────────┘  └─────────────────┘  │  Notion         │
         │                    │            │                 │
         │ Tailscale          │            └─────────────────┘
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│   ASH-1 VPS      │  │  Delivery       │
│   2GB            │  │                 │
│                  │  │  Telegram       │
│  Home Assistant  │  │  Discord        │
│  Wall Dashboard  │  │  WebUI          │
│  ha-fusion       │  │                 │
└─────────────────┘  └─────────────────┘
```

### Data Flow — A Turn in Hermes

```
User message (Telegram)
  │
  ▼
Gateway receives
  │
  ├─► B-full: search cold store (Supabase pgvector) ≥0.80 → inject relevant facts
  ├─► Patches: write gate, delegation nudge, domain ownership checkpoints arm
  │
  ▼
Agent runtime
  │
  ├─► Skills loaded (trigger-based matching)
  ├─► Memory injected (MEMORY.md + USER.md)
  ├─► Tools available (terminal, file, web, browser, kanban, delegation, MCP servers)
  │
  ▼
Response → Gateway → Telegram
  │
  ▼
Session ends
  ├─► session-end-offload.py: probe MEMORY.md ≥85% → store TRIM-SAFE facts to Supabase
  └─► session_distill.py (cron): extract decisions/outcomes → Supabase digests
```

## Branches

| Branch | Host | What |
|---|---|---|
| `main` | Mac Mini | Full Hermes — this branch |
| `mac-studio` | Mac Studio | Ollama inference node, dashboard client |
| `vps` | HIL-1 + ASH-1 | Remote fleet overview, topology, ownership |

## Key Files

| Path | Purpose |
|---|---|
| `AGENTS.md` | Agent rules — write gate, delegation, coding gates, memory hygiene |
| `SOUL.md` | Operating principles — how Hermes carries itself |
| `MEMORY.md` | Hot memory — durable facts injected every turn |
| `config/config.yaml` | Live configuration (providers, models, MCP servers, hooks, memory caps) |
| `scripts/offload_probe.py` | Memory probe — classifies facts as TRIM-SAFE / POINTER / KEEP-HOT |
| `scripts/session-end-offload.py` | Session-end hook — stores candidates to Supabase |
| `scripts/session_distill.py` | Session distillation — extracts decisions into searchable digests |
| `scripts/knowledge.py` | Knowledge store client — hybrid search against Supabase pgvector |
| `patches/` | Runtime monkey-patches — write gate, delegation checkpoint, domain ownership |
| `skills/` | 150+ agent skills — coding, devops, home automation, creative, research |
| `references/topology.json` | Single source of truth — host IPs, specs, models, profiles |
| `references/infrastructure-summary.md` | Detailed infrastructure overview |
| `references/domain-ownership.json` | Host → Hermes profile ownership mapping |
