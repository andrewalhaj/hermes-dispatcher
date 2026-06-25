# hermes-dispatcher — POLA Refactor Inventory (§5.1)

**Repo:** `/root/hermes-dispatcher` @ HEAD `3b0993e`, branch `master` (clean).
**Phase:** Inventory only — NO EDITS made. Awaiting greenlight per §5.2.
**Method:** 4-way parallel read-only audit (backend routing done inline after subagent timeout).

---

## A. Route map (net URL ground truth)

Net URLs all resolve under `/api/*` — **but `server.py` alone cannot predict them.** The `/api` prefix is applied 3 different ways:

- **(P) server.py owns prefix** — `include_router(x, prefix="/api")`, router declares bare paths.
- **(B) baked into router** — router declares `APIRouter(prefix="/api/...")`, server.py mounts with no prefix.
- **(F) full path in decorator** — `@chat_router.post("/api/chat/send")`, no prefix anywhere.

| Net URL | Method | Declaring file | Prefix source |
|---|---|---|---|
| /api/auth/login | POST | auth.py:28 | P (server:71) |
| /api/auth/logout | POST | auth.py:49 | P |
| /api/auth/check | GET | auth.py:56 | P |
| /api/health | GET | server.py:79 | P (api_router) |
| /api/logs | GET | logs.py:87 | P (server:88) |
| /api/logs/stream | GET | logs.py:100 | P |
| /api/settings | GET/PUT | settings.py:41,78 | P (server:91) |
| /api/settings/models | GET | settings.py:128 | P |
| /api/profiles | GET | settings.py:151 | P ⚠️ **DUP** |
| /api/insights | GET | insights.py:32 | P (server:94) |
| /api/skills | GET/POST | skills.py:122,237 | P (server:97) |
| /api/skills/{id} | GET/PUT/DELETE | skills.py:146,175,249 | P |
| /api/skills/{id}/enabled | PUT | skills.py:196 | P |
| /api/sessions | GET | sessions.py:54 | P + router prefix `/sessions` (server:100) |
| /api/sessions/search | GET | sessions.py:70 | P |
| /api/sessions/{id}/messages | GET | sessions.py:103 | P |
| /api/sessions/{id} | DELETE | sessions.py:125 | P |
| /api/search | GET | search.py:177 | P + router prefix `/search` (server:103) |
| /api/agents | GET | agents.py:106 | **B** (router prefix `/api/agents`, server:106 no prefix) |
| /api/agents/fleet | GET | agents.py:196 | **B** |
| /api/overview | GET | overview.py:88 | P (server:109) |
| /api/system | GET | system.py:205 | P (server:112) |
| /api/workspace/ls | GET | workspace.py:27 | P (server:115) |
| /api/workspace/read | GET | workspace.py:58 | P |
| /api/memory/files | GET/PUT | memory.py:195,218 | **B** (router prefix `/api/memory`, server:118 no prefix) |
| /api/memory/galaxy | GET | memory.py:243 | **B** |
| /api/memory/honcho-refresh | POST | memory.py:303 | **B** |
| /api/chat/send | POST | chat.py:37 | **F** (full path, server:121 no prefix) |
| /api/chat/cancel | POST | chat.py:81 | **F** |
| /api/chat/sessions | GET | chat.py:94 | **F** |
| /api/chat/sessions/{id}/messages | GET | chat.py:118 | **F** |
| /api/profiles | GET | chat.py:149 | **F** ⚠️ **DUP of settings.py** |
| /api/models | GET | chat.py:161 | **F** |
| /api/chat/upload | POST | upload.py:16 | **B** (router prefix `/api/chat`, server:127 no prefix, **guarded import**) |
| /api/kanban/tasks | GET/POST | kanban.py:101,136 | **B** (router prefix `/api/kanban`, server:132 no prefix) |
| /api/kanban/tasks/{id} | PATCH | kanban.py:111 | **B** |
| /api/kanban/stream | GET | kanban.py:155 | **B** |
| /api/kanban/agent-reports/{profile} | GET | kanban.py:190 | **B** |
| /api/media | GET | media.py:10 | P (server:135) |
| /api/cron | GET | cron.py:38 | **B** (router prefix `/api/cron`, server:138 no prefix) |
| /api/cron/output | GET | cron.py:80 | **B** |
| /api/cron/{job_id}/output | GET | cron.py:112 | **B** |
| /{full_path:path} | GET | server.py:145 | SPA catch-all (serves app/dist/) |

---

## B. Backend routing & run-path findings

| id | class | file:line | wrong guess a reader makes | proposed fix | behavior-preserving | greenlight |
|---|---|---|---|---|---|---|
| B1 | 3B prefix inconsistency | server.py:105,118,121,127,132,138 | "all routers mount with `prefix='/api'`" — actually agents/memory/chat/upload/kanban/cron bake it in | pick ONE convention: routers declare bare paths, server.py owns single `prefix='/api'`. Strip baked prefixes from the 6 router files, add `prefix='/api'` at their `include_router`. **Net URLs byte-identical** — prove with route-map diff (§6). | y | y |
| B2 | one-job-3-ways imports | server.py:120 (`chat_router`), 137 (`from routes import cron`), rest (`as x_router`) | reader expects one import idiom | unify to `from routes.x import router as x_router` for all | y | y |
| B3 | duplicate route | settings.py:151 vs chat.py:149 both → `/api/profiles` | reader edits one `/api/profiles` handler, other is the live one. settings_router (server:91) registers before chat_router (server:121) → **settings wins, chat.py:149 is dead** | remove the dead duplicate (chat.py:149) OR rename; confirm which the SPA calls first | y | y |
| E1 | run-path port mismatch | server.py:171 (port 8000) vs start-server.sh:8 / systemd / README (8787) | `python server.py` behaves like the real server — it binds 8000 instead of 8787 | change `__main__` default to 8787 (matches operational) OR delete the misleading `__main__`. **Port pin in start-server.sh is infra — do NOT touch.** | y | y |
| B4 | silent fallback | server.py:125-129 | upload route always present | guarded try/except prints to stdout and silently disables `/api/chat/upload` if python-multipart missing. Legible enough but the degrade is invisible to a client. Document the contract; multipart is in requirements.txt so confirm it's not actually firing. | y | y |
| B5 | stale module docstring | server.py:7-10 | invites "parallel worker cards to fill in routes via include_router(..., prefix='/api')" — this docstring is the *cause* of B1; it tells future authors to use prefix='/api' while half the tree ignores it | rewrite docstring to state the chosen single convention | y | y |

---

## C. Auth & security findings (FLAG + propose; scheme changes gated, separate batch)

| id | class | file:line | wrong guess | in-scope fix (make surface honest) | scheme-change (separate, gated) | greenlight |
|---|---|---|---|---|---|---|
| A1 | doc lies about crypto | README ("bcrypt") vs auth.py:32 `hashlib.sha256().hexdigest()` (unsalted); README setup cmd itself writes SHA-256 | "passwords are bcrypt-hashed" | correct README to say "SHA-256 (unsalted)" — single source of truth | upgrade to salted KDF (bcrypt/argon2) | y (doc) |
| A2 | committed secret | `.dashboard_passwd_hash` (64-hex SHA-256) git-tracked (commit db3ad41); .gitignore "secrets — NEVER commit" block doesn't cover it | "secrets are gitignored" | add `.dashboard_passwd_hash` to .gitignore | rotate credential; history rewrite = its own gated decision (do NOT silently rewrite) | y |
| A3 | token lifecycle | auth.py:3 docstring "ephemeral by design"; auth.py:17 module-level `secrets.token_hex(32)` (one global), logout (auth.py:49) deletes cookie only | "each client has its own expiring session" — actually all clients share ONE process-global token, never expires, logout is client-side only (valid server-side until restart) | document the model precisely at the call site | per-session tokens + server-side expiry | y (doc) |
| A4 | CORS over-permissive | server.py:37-42 + memory.py:314-318 `allow_origins=["*"]` on cookie-authed app, no intent comment | "CORS is restricted to trusted origins" | add comment stating the trusted-network assumption | tighten to explicit origins + config | y (doc) |

---

## D. Frontend findings (component graph, duplication, naming)

**Orphaned code (~1,290 LOC, no live import — confirmed by grep):**
- `BackgroundStars.tsx` (107 LOC) — homonym dup; only `StarsBackground.tsx` (201 LOC) is rendered.
- `Profiles.tsx` (406 LOC) — full panel, never wired to Shell nav / PanelId enum.
- `Workspace.tsx` (338 LOC) — nav header exists, no route handler; component unused.
- `overview/SparklesCore.tsx` — exported, never imported.
- `overview/useSystemMonitor.ts` — hook defined, unused (SystemMonitorTile uses `useSystemStats`).

| id | class | file | wrong guess | proposed fix | behavior-preserving | greenlight |
|---|---|---|---|---|---|---|
| D1 | homonym dup | BackgroundStars.tsx vs StarsBackground.tsx | "both used / interchangeable" | confirm BackgroundStars orphan via grep, remove (greenlight) or rename | y | y |
| D2 | orphan panels | Profiles.tsx, Workspace.tsx, Placeholder.tsx | "these panels are live" | mark dead/remove, OR document why unwired | y | y |
| D3 | live-vs-mock | src/data/*.ts + MOCKDATA_SPEC.md | README/spec implies 14 live panels; only **9 fetch real `/api/*`** (Overview, Chat, Kanban, Insights, Sessions, Memory, Logs, Settings, Skills); Agents = hybrid mock+live, Memory galaxy = mock+live | README/spec honesty fix only — do NOT wire endpoints this pass | y (doc) | y |
| D4 | one-job-3-ways | localStorage: Settings.tsx wrapper, Chat.tsx direct, SystemMonitor.tsx direct | "one canonical persistence helper" | unify to single lsGet/lsSet util | y | y |
| D5 | silent swallow | Memory/Logs/Sessions `.catch(()=>{})` | "fetch errors surface to UX" | make failures legible (out of scope to fully fix — flag) | y | y |

---

## E. Two-frontends + root artifacts + doc contradictions

**Two frontends (seed C):** backend serves ONLY `app/dist/` (React SPA). Root ships a SECOND standalone DC-framework dashboard:
- `Hermes Task Dispatcher.dc.html` (245KB, spaces in name), `support.js` (53KB generated "dc-runtime", header "do not edit"), `hermes-board-v2-inline.js` (81KB generated).
- **`grep server.py routes/` → 0 references.** Classification: **confirmed-orphan from the server's POV, but git-tracked.** Disposition: label + README pointer (it's a legacy/offline build), OR remove (greenlight, zero live refs proven).

**Root scratch artifacts:** 9× `_verify_*.py`, 4× `.task_*`, 2× `.*.log`, `__pycache__/`, `.serena/` — all **gitignored, NOT git-tracked, zero references.** Disposition: safe local cleanup (greenlight); `__pycache__`/`.serena` are tool-generated, leave.

**Doc-vs-code contradictions:**
| id | doc loc | claim | reality | fix | greenlight |
|---|---|---|---|---|---|
| E2 | README | "self-hosted on Mac Mini" | host is Linux x86_64 (`andrew-Macmini 7.0.12-1-t2-noble`), paths `/root/.hermes`, systemd unit | reconcile prose (paths/unit are infra — document, don't change) | y (doc) |
| (A1 dup) | README | "bcrypt" | SHA-256 — see C/A1 | — | — |

---

## Proposed commit slices (§5.3 — one astonishment class per commit, reversible)

**Batch 1 — behavior-preserving (after greenlight):**
1. `routing: single /api prefix convention` — B1+B5 (strip baked prefixes from 6 routers, server.py owns prefix; route-map diff proves byte-identical).
2. `routing: unify router import idiom` — B2.
3. `routing: remove dead duplicate /api/profiles` — B3.
4. `run: __main__ port 8000→8787 to match operational` — E1.
5. `docs: README truth pass` — A1 (sha256), E2 (Linux host), D3 (live-vs-mock panel table).
6. `security: gitignore committed password hash` — A2 (ignore only).
7. `docs: document session-token + CORS model at call site` — A3, A4 comments.
8. `frontend: remove orphaned components` — D1, D2 (greenlight, grep-proven dead).
9. `frontend: unify localStorage helper` — D4.
10. `chore: classify/remove two-frontends + root scratch` — E (label or remove).

**Batch 2 — scheme changes (separate, each its own written proposal + greenlight):**
- A1b salted KDF, A2b credential rotation/history, A3b per-session tokens, A4b CORS tightening.

**Verification per §6:** route-map diff (before/after byte-identical), `python -c "import server"` clean, `cd app && npm run build`, `npm run lint` no new errors, grep zero-refs before any delete.
