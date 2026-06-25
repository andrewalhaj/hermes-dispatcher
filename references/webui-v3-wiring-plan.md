# Hermes WebUI v3 (hermes-react) — Backend Wiring Plan

**Date:** 2026-06-18. **Directive (Andrew):** Redo hermes.andrewskingdom.com. Do NOT change
a single thing about the front end. Adapt/rebuild the BACKEND to fit the front end. If live
data cannot be wired, leave the dummy and say so. **Chosen path: B (wire via data layer only).**

## THE DECISIVE FACT
The v3 front end (`Hermes WebUI Design (3).zip` → `hermes-react/`) makes **ZERO API calls**.
No `fetch`, no `EventSource`, no api client. Only `/api/` string in the whole tree is text
inside a fake log row (`mockData.ts:92`). Every panel renders static arrays held in React
context. So "wire live data without touching the front end" is literally impossible — there
is no fetch seam. Andrew greenlit Path B: edit ONLY the 3 data-plumbing files (identical
render), build the backend to fit, leave dummy where no seam exists and name it.

## Source of truth
- Immutable design copy: `/tmp/webui-design/hermes-react/` (extracted from the zip) and the
  zip itself at `/root/.hermes/cache/documents/doc_d5380c3796d5_Hermes WebUI Design (3).zip`.
- Working build dir: `/root/projects/hermes-ui-fresh/` (exact rsync of the zip; baseline
  `npm run build` = GREEN, dist/ ~1.5MB js). Restore any file from the zip if corrupted.

## Panel → data-source map (THIS zip, verified by reading every panel)
| Panel | Reads from | Wireable via 3 files? | After wiring |
|---|---|---|---|
| Overview | `useHermes()` store | YES | LIVE (real tasks+agents) |
| Kanban | `useHermes()` store | YES | LIVE (real board, drag→PATCH, SSE) |
| Agents | `useHermes()` store | YES | LIVE (derived from kanban runs + sessions) |
| Settings | `useHermes()` (accent) | n/a | Works (accent = client pref by design) |
| Logs | `import {LOGS}` const (mockData) | YES (bootstrap) | LIVE (gateway journal) |
| MemoryGalaxy | `import {MEMORIES}` const (mockData) | YES (bootstrap) | LIVE (6-tier projection) |
| Chat | `useHermes()` for agent list only | PARTIAL | agent list LIVE; convo+send are in-panel mock |
| Insights | inline `const ACTIVITY/MODELS/KPIS` IN PANEL | NO seam | DUMMY (real data exists) |
| Skills | inline `const SKILLS` IN PANEL | NO seam | DUMMY (real data exists) |

**Result with strict 3-file scope: 6 fully LIVE, 1 PARTIAL (Chat), 2 DUMMY (Insights, Skills).**
Insights/Skills/Chat-convo have NO data-layer seam (mock lives inside the panel .tsx). Wiring
them requires editing those panel files — a data-only edit that renders identically — which is
OUTSIDE the 3-file scope Andrew approved. Offer it as an opt-in; do not do unprompted.

## The mechanism: server-side bootstrap injection (no front-end touch)
Logs+MemoryGalaxy read module-level consts SYNCHRONOUSLY at first render — async loaders
won't re-render them. Fix: backend injects `window.__HERMES_BOOTSTRAP__ = {...real snapshot}`
into the SERVED index.html at request time (string substitution on the built artifact, NOT
source). `mockData.ts` reads that global synchronously to build TASKS/AGENTS/MEMORIES/LOGS,
falling back to the original dummy arrays when the global is absent (so `npm run dev` standalone
still works). Auth-gated: unauthed request → dummy bootstrap (no data leak); authed → real.

## Files I will edit (the 3 authorized + backend — NEVER a panel/component/css)
1. **`src/lib/api.ts`** (NEW) — typed fetch (same-origin, CSRF header on writes, AbortController
   timeout, ApiError surfacing 401), `subscribeSSE(path,onMsg)`, `readBootstrap()`.
2. **`src/lib/mockData.ts`** — replace seed literals with builders reading
   `window.__HERMES_BOOTSTRAP__` ?? original-dummy. Houses the 6-tier galaxy projection
   (notes←MEMORY split on \n§\n, profile←USER, soul←SOUL by heading, context←AGENTS,
   facts←skills, convos←recent sessions; seeded-LCG gas() jitter for stable layout) and raw
   log-line parsing. Keep `export const TASKS/AGENTS/MEMORIES/LOGS` names intact.
3. **`src/lib/store.tsx`** — seed tasks/agents from real mockData; real `moveTask` (PATCH
   /api/kanban/tasks/{id}, optimistic + rollback, reject running drop), real `runDispatcher`
   (POST /api/kanban/dispatch), SSE board refresh. SUPERSET of original interface so every
   panel still type-checks untouched.
4. **`server.py`** (REBUILD, backed up) — FastAPI serving dist/ + auth-gated bootstrap
   injector + real endpoints matching the EXACT front-end types:
   - `GET /api/kanban/board` → tasks[] in Task shape (id,title,priority,status,tenant,assignee,
     skills[],branchName,parents[],description,comments[],events[],runs[],links[]).
   - `GET /api/kanban/tasks/{id}` → detail (comments/events/runs/links from aux tables).
   - `PATCH /api/kanban/tasks/{id}` {status} → move (reject running; mirror bridge).
   - `POST /api/kanban/dispatch` → runDispatcher target.
   - `GET /api/kanban/events/stream` → SSE diff by latest event id.
   - `GET /api/memory` → {memory,user,soul,context} text blobs (galaxy source).
   - `GET /api/insights` → real totals+models+activity from state.db (for the OPTIONAL Insights wire).
   - `GET /api/skills` → 153 real skills (for the OPTIONAL Skills wire).
   - `GET /api/sessions`, `GET /api/logs`, `GET/POST /api/settings`, `GET /api/health/agent`,
     `POST /api/auth/login|logout`, `GET /api/auth/status`.
   - Real data sources: kanban.db (tasks+task_links+task_comments+task_events+task_runs),
     state.db (579 sessions: tokens/cost/models), ~/.hermes/memories/*.md + SOUL/AGENTS, skills/.

## Honest reality notes (tell Andrew)
- Live board is sparse vs the mock: 17/20 done, 2 ready, 1 blocked, all one tenant
  (DM Voice Board), no running task right now, skills column null on most. So Kanban will look
  Done-heavy and skill chips mostly empty — that's the real state, not a bug.
- Agents panel: real names/models/assignment + success% computed from task_runs; latency has
  no queryable source → derived/approx (flagged).
- Insights $769.71 / 13.5M tokens / model split is REAL and ready — only the panel's inline
  mock blocks it. Same for Skills (153 real).

## Deploy (ALL gated)
- Build hermes-ui-fresh → dist/. Rewrite server.py. Stand up side-by-side on a NEW port behind
  same auth; CDP-screenshot-verify every panel shows REAL data (real task titles, real $769,
  real memory count) BEFORE cutover.
- Cutover = repoint systemd unit (WorkingDirectory/EnvironmentFile) OR rsync into live dir +
  `systemctl restart hermes-webui`. Backup old server.py + unit first. Blips the live session.
- index.html placeholder/cache-key traps: it's a Vite build (hashed asset names) so the frozen
  ?v= trap doesn't apply the same way, but verify served asset hash == freshly built hash.

## Verify before "done"
Per panel via CDP against the live render: REAL data visible, not selector counts. Pixel-sample
for white-screen check. WebGL throws in headless (no GPU) — galaxy degrades to fallback; that's
expected, not a bug.
