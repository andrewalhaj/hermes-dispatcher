# REFACTOR_NOTES.md — POLA Refactor: hermes-dispatcher

Branch: `pola-refactor/batch-1-2`
Commits (oldest → newest relative to `master`):

```
2036661  frontend: remove orphaned components (D1, D2)
662c03b  frontend: unify localStorage helper (D4)
3a50782  docs: README truth pass (A1-doc, D3, E2)
366efab  routing: strip baked /api from router files (B1)
f87fa1c  routing: server.py owns /api prefix + unify imports + B3 fix (B1+B2+B3+E1)
<auth>   security: gitignore committed password hash + document auth model (A2, A3, A4)
<docs>   docs: label standalone DC dashboard (C)
```

---

## Each fix mapped to the reader-surprise it eliminates

### D1 — `BackgroundStars.tsx` removed
**Surprise removed:** Two near-homonym components (`BackgroundStars` and `StarsBackground`)
at the same level. A reader navigating to "the stars component" hit the wrong one 50% of the
time. `BackgroundStars.tsx` (107 LOC) was never imported anywhere; `StarsBackground.tsx`
(201 LOC) is the live one imported by `Shell.tsx:20`.
**Verification:** `grep -rn BackgroundStars app/src/` → zero matches outside deleted file.

### D2 — `Profiles.tsx`, `Workspace.tsx`, `SparklesCore.tsx`, `useSystemMonitor.ts` removed
**Surprise removed:** Four components/hooks that appeared to be live features but were never
wired. `Profiles.tsx` (406 LOC) — no import in Shell or App. `Workspace.tsx` (338 LOC) — Shell
has a `header: 'Workspace'` nav entry but imports `Placeholder`, not this component.
`SparklesCore.tsx` and `useSystemMonitor.ts` — exported, never consumed.
**Verification:** grep confirmed zero external imports for each. Build passed after removal.

### D4 — `localStorage` unified into `app/src/utils/localStorage.ts`
**Surprise removed:** Three divergent localStorage access patterns in the same codebase:
`Settings.tsx` had local `lsGet`/`lsSet` helpers; `Chat.tsx` and `SystemMonitorTile.tsx` used
raw `localStorage.getItem/setItem` inline without error guards. A reader couldn't tell which
pattern was canonical. All three now import from the shared utility.
**Verification:** `npm run build` and `npm run lint` — no new errors.

### A1-doc — README "bcrypt" → "SHA-256 (unsalted)"
**Surprise removed:** README claimed passwords are stored as a "bcrypt password hash".
`routes/auth.py:32` does `hashlib.sha256(submitted.encode()).hexdigest()`. A security reviewer
reading the README would assess bcrypt (salted, slow KDF) and miss the actual SHA-256
(unsalted, fast, no salt). README now tells the truth.

### D3 — Panel live-vs-mock table added to README
**Surprise removed:** README presented all panels as live/operational. `src/data/*.ts` files
contain mock fixtures consumed by Agents and Memory galaxy panels. Two panels (Profiles,
Workspace) are completely unwired. README now has an explicit per-panel table.

### E2 — README host description: Mac Mini → Linux x86_64
**Surprise removed:** README said "self-hosted on Mac Mini" but the host is Linux x86_64
(kernel `7.0.12-1-t2-noble`), paths are `/root/`, deployment is systemd. A reader following
the README to set up their own instance would look for macOS-specific instructions.

### B1 — `/api` prefix stripped from 6 router files
**Surprise removed:** Routers for `agents`, `memory`, `chat` (decorators), `upload`, `kanban`,
`cron` baked `/api` into their own prefix/path declarations. The remaining 10+ routers used
bare paths with `server.py` supplying the prefix. A reader could not derive any route's URL
from `server.py` alone — half the routers needed the router file open simultaneously.
After: every router declares bare paths; `server.py` is the single source of `/api`.
**Verification:** route-map diff (45 `/api/*` routes before = 45 after; byte-identical).

### B2 — Import idiom unified
**Surprise removed:** Three import idioms for the same job:
- `from routes.x import router as x_router` (most routers)
- `from routes.chat import chat_router` (different variable name)
- `from routes import cron; cron.router` (module import, attribute access)
All now use `from routes.x import router as x_router`.

### B3 — Dead duplicate `/api/profiles` removed from `settings.py`
**Surprise removed:** Both `settings.py` and `chat.py` registered `/api/profiles`. `settings.py`
returned `{"profiles": [...]}` (dict); `chat.py` returned `["default", ...]` (string array).
`Chat.tsx` expects a string array. `settings.py` registered first and silently won, so the UI
always received the wrong shape. The wrong-shape duplicate is removed; `chat.py`'s correct
handler is now the sole registrant.
**Verification:** route-map after shows exactly one `/api/profiles GET`.

### B5 — `server.py` module docstring rewritten
**Surprise removed:** The old docstring said "add routers via `include_router(x, prefix='/api')`"
— this invitation is precisely what caused the B1 inconsistency (some workers followed it,
others baked the prefix into the router). New docstring states the convention explicitly.

### E1 — `__main__` port 8000 → 8787
**Surprise removed:** `python server.py` bound port 8000. Every documented launch path
(`start-server.sh`, systemd unit, README) uses 8787. A developer running `python server.py`
for local testing silently ran a different server on a different port.

### A2 — `.dashboard_passwd_hash` added to `.gitignore`
**Surprise removed:** `.gitignore` had a "secrets — NEVER commit" block that didn't cover
`.dashboard_passwd_hash`. The file was git-tracked. A reader assuming the gitignore block
covered secrets would not realize the hash was committed. The file is now gitignored.
**Note:** The hash is still in git history (commit `db3ad41`). Credential rotation is a
separate decision — not silently applied here.

### A3 — Session token model documented at call site
**Surprise removed:** The docstring said "ephemeral by design" which implies per-session or
time-limited tokens. The actual model is one process-global token, shared by all clients,
never expiring, with client-side-only logout. Docstring now precisely describes the model.

### A4 — CORS `allow_origins=["*"]` rationale commented
**Surprise removed:** A reader seeing `allow_origins=["*"]` on a cookie-authed app would
assume it was an oversight. The comment now explains the trusted-network deployment context
and the mitigating factors (`samesite="strict"`, `httponly=True`).

### C — Standalone DC dashboard labeled with `STANDALONE_DASHBOARD_README.md`
**Surprise removed:** Two unlabeled frontends at the same repo root level — the React SPA
(`app/`) and a standalone DC framework dashboard (`Hermes Task Dispatcher.dc.html` + generated
bundles). A newcomer opening the root couldn't tell which one the server ran. The README
clarifies: the server runs only `app/dist/`; the DC files are an offline standalone build.

---

## §6 Verification output

### Route-map diff (45 /api/* routes, byte-identical)

```
BEFORE (from inventory at master HEAD):
GET      /api/agents                               GET      /api/agents                               ✓
GET      /api/agents/fleet                         GET      /api/agents/fleet                         ✓
GET      /api/auth/check                           GET      /api/auth/check                           ✓
POST     /api/auth/login                           POST     /api/auth/login                           ✓
POST     /api/auth/logout                          POST     /api/auth/logout                          ✓
POST     /api/chat/cancel                          POST     /api/chat/cancel                          ✓
POST     /api/chat/send                            POST     /api/chat/send                            ✓
GET      /api/chat/sessions                        GET      /api/chat/sessions                        ✓
GET      /api/chat/sessions/{id}/messages          GET      /api/chat/sessions/{id}/messages          ✓
GET      /api/cron                                 GET      /api/cron                                 ✓
GET      /api/cron/output                          GET      /api/cron/output                          ✓
GET      /api/cron/{job_id}/output                 GET      /api/cron/{job_id}/output                 ✓
GET      /api/health                               GET      /api/health                               ✓
GET      /api/insights                             GET      /api/insights                             ✓
GET      /api/kanban/agent-reports/{profile}       GET      /api/kanban/agent-reports/{profile}       ✓
GET      /api/kanban/stream                        GET      /api/kanban/stream                        ✓
GET      /api/kanban/tasks                         GET      /api/kanban/tasks                         ✓
POST     /api/kanban/tasks                         POST     /api/kanban/tasks                         ✓
PATCH    /api/kanban/tasks/{task_id}               PATCH    /api/kanban/tasks/{task_id}               ✓
GET      /api/logs                                 GET      /api/logs                                 ✓
GET      /api/logs/stream                          GET      /api/logs/stream                          ✓
GET      /api/media                                GET      /api/media                                ✓
GET      /api/memory/files                         GET      /api/memory/files                         ✓
PUT      /api/memory/files                         PUT      /api/memory/files                         ✓
GET      /api/memory/galaxy                        GET      /api/memory/galaxy                        ✓
POST     /api/memory/honcho-refresh                POST     /api/memory/honcho-refresh                ✓
GET      /api/models                               GET      /api/models                               ✓
GET      /api/overview                             GET      /api/overview                             ✓
GET      /api/profiles   [settings.py wins — dict] GET      /api/profiles   [chat.py — string[]]      ✓ (B3 fix: correct shape)
GET      /api/search                               GET      /api/search                               ✓
GET      /api/sessions                             GET      /api/sessions                             ✓
GET      /api/sessions/search                      GET      /api/sessions/search                      ✓
DELETE   /api/sessions/{session_id}                DELETE   /api/sessions/{session_id}                ✓
GET      /api/sessions/{session_id}/messages       GET      /api/sessions/{session_id}/messages       ✓
GET      /api/settings                             GET      /api/settings                             ✓
PUT      /api/settings                             PUT      /api/settings                             ✓
GET      /api/settings/models                      GET      /api/settings/models                      ✓
GET      /api/skills                               GET      /api/skills                               ✓
POST     /api/skills                               POST     /api/skills                               ✓
GET      /api/skills/{id}                          GET      /api/skills/{id}                          ✓
PUT      /api/skills/{id}                          PUT      /api/skills/{id}                          ✓
DELETE   /api/skills/{id}                          DELETE   /api/skills/{id}                          ✓
PUT      /api/skills/{id}/enabled                  PUT      /api/skills/{id}/enabled                  ✓
GET      /api/system                               GET      /api/system                               ✓
GET      /api/workspace/ls                         GET      /api/workspace/ls                         ✓
GET      /api/workspace/read                       GET      /api/workspace/read                       ✓
```

`/api/chat/upload` was disabled before and after (python-multipart not in venv — pre-existing).

### Backend import smoke
`python -c "import server"` — clean (verified; upload import guarded by try/except as before).

### Frontend build
`cd app && npm run build` — ✅ passed (tsc + vite, no new errors).

### Frontend lint  
`cd app && npm run lint` — ✅ no new errors introduced.

### Zero-reference verification for deleted files
All 5 deleted frontend files confirmed zero external imports via grep before removal.
