# Wiring a standalone React/Vite frontend to the real Hermes backend

When the design handoff is NOT a `.dc.html` to port into the vanilla-JS app, but a
**complete standalone front-end** (Vite + React + TS + Tailwind v4, Framer Motion,
React Three Fiber, dnd-kit, Recharts) with **mocked data**, the job is: replace the
mocks with real `/api/*` calls **without changing the visual design**. This is a
different workflow from the vanilla-JS skin/panel edits — there IS a build step, a
type system, and a data layer to preserve.

Proven 2026-06-18 wiring `hermes-react/` (the `Hermes WebUI Design` handoff) to the
live backend on :8787. All panels verified rendering real data via CDP.

## The shape of the handoff
A README (authoritative — read its "Wiring" section first) + `src/lib/` with:
- `types.ts` — domain types you MUST preserve (Task, Agent, Memory, LogEntry…).
- `mockData.ts` — seed arrays to REPLACE with async loaders.
- `store.tsx` — a single context provider holding panel/accent/tasks/agents +
  actions (moveTask, runDispatcher) to REPLACE with real API calls + SSE.
- `theme.ts` — palette/threshold helpers (priorityColor, TIER_META centers). The
  source of truth for colors — do not introduce new hex outside this.
- panels under `components/panels/` — some read `useHermes()` (auto-wired once the
  store is real), others import a mock array directly (Logs, MemoryGalaxy) or have
  inline mocks (Insights, Skills) — those need per-panel edits.

## FIRST: does the front end make ANY API calls? (the zero-fetch fork)
Before planning ANY wiring, grep the handoff for a fetch seam:
`grep -rn "fetch\|EventSource\|axios\|XMLHttpRequest\|/api/" src/`. A design-tool
handoff (Claude Design / "Hermes WebUI Design" zip) is frequently a PURE MOCK app —
**zero** `fetch`/`EventSource`, every panel renders module-level const arrays held in
React context. Seen 2026-06-18 (v3 zip): the ONLY `/api/` string in the whole tree was
text inside a fake log row. There is NO seam to plug a backend into.

When this is true, "wire live data without changing the front end" is literally
impossible — say so plainly and present a fork to the user via `clarify` BEFORE editing:
- **Path A (strict literal):** touch nothing in the front end → ships the exact design
  with 100% dummy data behind auth. Zero design risk, zero real data.
- **Path B (the real ask):** edit ONLY the data-plumbing files (`mockData.ts`,
  `store.tsx`, new `api.ts`) → identical render, real data flows. This is almost always
  what the user actually wants when they say "adapt the backend to this front end."
The visual design (`.tsx`/css/layout) stays pixel-identical in BOTH paths — only the 3
plumbing files differ. Frame the gate exactly that way; it's the honest reading of
"don't change a single thing about the front end" + "wire in live data."

## Panel data-source split — map it before scoping (THREE categories, not two)
Read every panel's imports first; data consumption splits THREE ways, and only the
first two are reachable from the 3 plumbing files:
1. `useHermes()` store → wire `store.tsx` (Overview, Kanban, Agents, Settings, Chat-agent-list).
2. `import { LOGS/MEMORIES } from mockData` const → wire `mockData.ts` (Logs, MemoryGalaxy).
3. **INLINE hardcoded mock IN the panel body** (`const ACTIVITY/MODELS/SKILLS = [...]`
   inside Insights.tsx / Skills.tsx) → NO data-layer seam. Wiring these REQUIRES editing
   the panel `.tsx` (a data-only edit that renders identically). If the user said "don't
   change the front end," category 3 is OUT of the 3-file scope — name it as DUMMY and
   OFFER the panel edit as an explicit opt-in. Don't silently edit panels, and don't
   silently leave real data on the floor; surface the tradeoff per panel.

## SYNCHRONOUS consts can't use async loaders → server-side bootstrap injection
Category-2 panels read module-level consts SYNCHRONOUSLY at first render. The reference's
"replace seeds with async loaders" guidance CANNOT feed a sync const — an async loader
resolves after the const is already evaluated. The proven fix (2026-06-18) is
**server-side bootstrap injection**, no front-end async needed:
1. Backend injects `<script>window.__HERMES_CONFIG__ = {...real snapshot}</script>` into
   the SERVED `index.html` at request time (string replace before `</head>` on the built
   artifact — NOT the source). Auth-gated: unauthed → empty/dummy bootstrap (no data
   leak); authed → real snapshot (kanban, agents, galaxy, logs, insights, skills).
2. `mockData.ts` reads `window.__HERMES_CONFIG__` synchronously: `export const TASKS =
   boot.kanban ?? [<original dummy>]`. Keep the original dummy arrays as the `??` fallback
   so `npm run dev` standalone still renders. The galaxy builder checks
   `boot.memories?.length` first (server pre-built) then falls back to the local 6/9-tier
   projection.
3. Cache the bootstrap server-side with a short TTL (~30s) and bust it on board mutations
   (PATCH/dispatch set `_bootstrap_ts = 0`) so the next page load is fresh.
This gives synchronous real data on first paint (no spinner flash) AND keeps the panels'
imports byte-identical. Category-3 panels (inline mock) additionally read the same global
(`readBootstrap().insights/.skills`) with a `useEffect` fetch fallback.

## Adding NEW Memory Galaxy tiers (beyond the original 6)
To add tiers (e.g. supabase, honcho, obsidian — done 2026-06-18) touch only:
1. `types.ts` MemoryTier union — append the new literals.
2. `theme.ts` TIER_META — add `{label,color,center:[x,y,z]}` per tier (pick 3D centers
   spaced from the existing 6 so clusters don't overlap).
3. `mockData.ts` + backend galaxy builder — add a source loader per tier. Real sources
   on this host: Supabase cold store at `~/.hermes/knowledge_db/knowledge.lance` (read via
   `import lance; lance.dataset(path).to_table(columns=[...]).to_pydict()` — 483 rows:
   id,text,source,stored_at,vector[768]); Honcho is `enabled=False` for live API (no
   app_id) BUT its peer-card + user-model are synced daily to the Obsidian vault at
   `~/Documents/Obsidian Vault/hermes-memories/honcho/{peer-card,user-model}.md` — parse
   those offline copies; Obsidian vault notes via `OBSIDIAN_VAULT_PATH` env (fallback
   `~/Documents/Obsidian Vault`), `rglob('*.md')`. Keep the seeded-LCG `gas()` jitter so
   layout is stable across reloads. NO component edit needed — MemoryGalaxy.tsx iterates
   `MEMORIES` and `TIER_META` generically.

## Real backend data sources on this host (kanban + insights)
- **kanban.db** (`~/.hermes/kanban.db`): `tasks` (id,title,body,assignee,status,priority,
  tenant,branch_name,skills[null|csv],created_at,started_at,completed_at — **NO `updated_at`
  column**; it's created_at/started_at/completed_at only). PITFALL (bit hard 2026-06-18):
  a `SELECT … updated_at` or `UPDATE tasks SET status=?, updated_at=?` throws
  `sqlite3.OperationalError: no such column: updated_at` — and because `_load_tasks()` wraps
  the query in try/except returning `[]`, the failure is SILENT: the board renders 0 tasks
  with no visible error, only a `WARNING _load_tasks failed: no such column: updated_at` in
  `journalctl -u hermes-webui`. ALWAYS `PRAGMA table_info(tasks)` against the LIVE db before
  writing any query — do not copy column lists from memory or another schema. For a move,
  `UPDATE tasks SET status=? WHERE id=?` (no updated_at).), `task_links` (parent_id,child_id) →
  parents[], `task_comments` (author,body,created_at), `task_events` (kind,payload,
  created_at — `kind` not `type`; payload is JSON with status/assignee), `task_runs`
  (id,profile,status,outcome,started_at — `outcome='completed'`→done). Skills column is
  NULL or CSV. created_at is unix SECONDS → ×1000 for JS ms.
- **state.db** (`~/.hermes/state.db`) for Insights: `sessions` has input_tokens,
  output_tokens, message_count, model, actual_cost_usd/estimated_cost_usd, started_at,
  archived. Real totals come straight from `SUM()` aggregates; model mix from
  `GROUP BY model`; activity-by-day from `GROUP BY date(started_at,'unixepoch')`.
- Agents panel has no dedicated store — DERIVE it: hermes orchestrator always first, then
  named worker profiles from `task_runs GROUP BY profile` with success% = completed/total.
  Latency has no queryable source → flag as derived/approx, don't fabricate a number.

## Step 0 — establish ground truth on BOTH sides before editing
1. `npm install && npx tsc -b` (real type-check, exit 0) + a `vite` smoke boot →
   confirm green baseline. The write-tool's per-file lint runs `tsc` WITHOUT the
   project tsconfig and floods false `Cannot find name 'Set'/'Map'/'Buffer'`
   errors — IGNORE those; trust only `npx tsc -b` against the real config.
2. **Probe the live API contract** — do not guess response shapes. Mint a session
   cookie and hit each endpoint, dumping keys. See
   `scripts/probe_backend_shapes.py` in this skill. The React mock is often
   modeled on the real board, but field names differ (e.g. task `body`→description,
   `branch_name`→branchName, `skills` is `null|csv`, parents come from
   `link_counts`, comments/events/runs only in the task-DETAIL endpoint).

## The endpoint map (confirmed live shapes)
- `GET /api/kanban/board` → `{columns:[{name,tasks[]}], tenants, assignees, latest_event_id, changed}`.
  Task fields: id,title,body,assignee,status,priority,tenant,branch_name,skills(null|csv),
  link_counts:{parents,children},comment_count,created_at. Columns: triage,todo,ready,running,blocked,done.
- `GET /api/kanban/tasks/{id}` → `{task, comments:[{author,body,created_at}], events:[{kind,payload,created_at}], runs:[...], links:{parents[],children[]}}`.
  NOTE events use `kind` not `type`; comments use `body`+`created_at` (seconds → ×1000 for JS ms).
- `POST /api/kanban/tasks/{id}` `{status}` → move. Running is rejected (claim_task-only).
- `POST /api/kanban/dispatch` → runDispatcher target.
- `GET /api/kanban/events/stream` → SSE; diff by `latest_event_id` cursor, re-fetch board on change.
- `GET /api/memory` → 4 text blobs `{memory,user,soul,project_context, *_mtime}` (NOT records).
- `GET /api/sessions` → `{sessions:[{title,model,message_count,updated_at,...}]}`.
- `GET /api/skills` → `{skills:[{name,description,category,disabled}]}`.
- `GET /api/insights?period=30` → `{total_sessions,total_messages,total_tokens,total_cost,models:[{model,sessions,...}],activity_by_day:[{day,sessions}],activity_by_hour}`.
- `GET /api/logs?tail=200` → `{lines:[str], file, ...}` — RAW strings, parse to LogEntry yourself.
- `GET /api/settings` → flat dict (theme,skin,language,bot_name,default_workspace,
  check_for_updates,api_redact_enabled,notifications_enabled,session_endless_scroll,webui_version,agent_version). POST a changed-key subset to save.
- `GET /api/health/agent` → `{alive,details:{gateway_state,active_agents}}`.

## The data layer (what to build)
1. **`src/lib/api.ts`** — typed fetch wrapper: JSON in/out, `credentials:'same-origin'`,
   CSRF header `X-Hermes-CSRF-Token` on writes (read from `window.__HERMES_CONFIG__.csrfToken`;
   treat the literal `__CSRF_TOKEN__` placeholder as absent), AbortController timeout,
   typed `ApiError` (surface 401 for the auth gate), and a `subscribeSSE(path,onMsg)` helper
   (EventSource, auto-reconnect). Plus `getAuthStatus/login/logout`.
2. **`src/lib/mockData.ts`** — replace seeds with async loaders returning the SAME
   types: `loadTasks` (board→Task[], parents seeded from link_counts count, real ids
   backfilled by `loadTaskDetail`), `loadAgents` (insights models + health → Agent[]),
   `loadMemories` (the 6-tier galaxy projection — see below), `loadLogs` (parse raw
   lines). Keep `export const TASKS/AGENTS/MEMORIES/LOGS = []` as empty fallbacks so
   existing imports stay valid.
3. **`src/lib/store.tsx`** — real `refresh()` on mount, `moveTask` (optimistic +
   rollback on API failure; reject DISPATCHER_OWNED locally), `runDispatcher` →
   `/api/kanban/dispatch` with a `dispatching` flag, and the SSE board subscription
   gated on `authed===true`. Expose `boardState`/`boardError`/`authed`/`setAuthed` —
   it's a superset of the original interface so panels still type-check.
4. **`src/lib/useAsync.ts`** — generic `useAsync(loader, fallback)→{data,status,error,reload}`
   for the panels that fetch directly (Memory, Logs, Insights, Skills, Overview).

## Memory Galaxy: port the PROVEN 6-tier projection
The React `Memory` type wants `{tier,importance,recall,ageDays,pos}` where `pos` is a
3D point. The vanilla app's `_loadGalaxyData` (static/panels.js ~6314) already produces
exactly this — PORT IT verbatim into `loadMemories`:
- notes←memory (split on `\n§\n`), profile←user, soul←soul (split by markdown heading),
  context←project_context, facts←skills (slice 18), convos←sessions (top 16 by recency).
- importance from text length + a HOT keyword regex; recall from title char variety;
  ageDays from `*_mtime`. `pos = TIER_META[tier].center + seeded gas() jitter * (1.55-imp*0.5)`.
  Use the React `theme.ts` tier centers, keep the seeded-LCG `gas()` algo for stable layout.

## Kanban contracts (honor these — the panel is auto-wired via the store)
- Running is dispatcher-owned: `DISPATCHER_OWNED` locks the column + shows "auto";
  `moveTask` rejects running drops (mirrors the bridge 400).
- `priorityColor()` thresholds (≥7 red, ≥5 amber, ≥3 blue, ≥1 violet), rendered `P{n}`.
- `parents[]` drives the ⛓ count from `link_counts.parents`.
- SSE diffs by `latest_event_id`.

## Production checklist (do these — they're real, not optional polish)
- **Auth gate**: a `Login` component (password → `POST /api/auth/login`), shown when
  the store's `authed===false` (set on a 401 from `refresh()`); splash on `null`.
- **Loading/error/empty states** on every data panel (spinner + Retry button bordered
  with `var(--ac)` + empty message). Reuse the design's color tokens only.
- **ErrorBoundary** (class component) wrapping the panel router AND the R3F `<Canvas>`.
  WebGL context creation THROWS in headless Chromium (no GPU) — the boundary degrades
  the galaxy to a "3D view unavailable · N records across M tiers" fallback instead of
  white-screening. It renders fine in a real browser; do not "fix" the WebGL error.
- **CSRF for production**: add `<script>window.__HERMES_CONFIG__={csrfToken:"__CSRF_TOKEN__",...}</script>`
  to `index.html` — the backend substitutes `__CSRF_TOKEN__` at request time when it
  serves `/` (routes.py ~7059). In dev the origin check (same-origin via the proxy)
  satisfies CSRF so the literal placeholder is harmless.
- **i18n**: if the design has no language control rendered, say so honestly — don't
  fabricate one. Full string-extraction is out of scope for "wire the data."
- **Color discipline**: every hex must come from `theme.ts` (+ the dark-on-accent text
  color already used, e.g. `#1c1404`). `grep -hoE '#[0-9a-fA-F]{6}'` your new files
  and diff against the theme palette before claiming "no color drift."

## Dev environment + live verification
- Add a vite dev proxy so the React app at :5180 reaches the real backend:
  `server.proxy['/api'] = { target:'http://127.0.0.1:8787', changeOrigin:true, ws:true }`.
  `changeOrigin:true` rewrites the Origin so backend CSRF/origin checks pass in dev.
- Run the dev server with `terminal(background=true)` (long-lived) — never `&`.
- **Verify against the LIVE render via CDP**, the same harness as the rest of this
  skill (`references/headless-visual-verify.md`): log in through the real auth gate,
  click the real nav, screenshot + probe `main.textContent`. Confirm REAL data shows
  (real task titles, real model names, real token totals, "N memories" count) — not
  your own selector counts. PIL pixel-sampling (dark bg + content density) confirms a
  panel rendered vs white-screened when vision is unavailable.

## PITFALL: do NOT delegate TSX fidelity authoring to a weak/local model
Burned 2026-06-18: delegated 4 panel rewrites to the Mac Studio (qwen2.5-32b) in a
`delegate_task` batch. 3 timed out at 900s; the 1 that "completed" returned MANGLED
JSX (a `boxShadow={...}` prop on a `<button>`, broken `.map()` destructuring, unclosed
tags) and corrupted the files. Restored from the attachment originals and authored
directly. Lesson: design-fidelity TSX/JSX authoring must stay on the strong main model
(Sonnet/Opus) — small local models mangle JSX structure. Delegation is fine for
parallel READ/analysis, not for precise multi-file code authoring where a wrong result
is worse than a slow one. Keep a pristine copy (the original handoff dir) so you can
restore after a bad delegation. If you must split work, give each subagent the EXACT
current file content + contract and verify every diff yourself with `tsc -b`.

Two concrete sub-failures seen again 2026-06-18 (second wiring of the same handoff,
delegated to qwen2.5-32b — same lesson, sharper detail):
- **A subagent will `patch` files it never `read_file`'d and fail every edit** with
  "Failed to read file" / "could not find old_string." It also worked the WRONG
  PATH (see nested-dir trap below) so the files it targeted didn't exist there. The
  subagent's own summary is a SELF-REPORT — it claimed roadblocks and "needs a
  developer," but the truth was a path + read-before-patch mistake, not a real
  blocker. Pick the task up directly and finish it; don't accept "this is too hard"
  from a weak model at face value.
- **The subagent misread node_modules type noise as a build blocker.** It saw the
  flood of `Cannot find name 'Set'/'Map'/'Buffer'/'Iterable'` from `@types/*` and
  concluded the project was broken / `vite.config.ts` was unresolvable. Those are
  the EXACT false errors Step 0 says to ignore — they're suppressed by
  `skipLibCheck:true` and never reach the real `tsc -b`/`vite build`. When you hand
  this task to a subagent, put "IGNORE node_modules .d.ts errors; only `npm run
  build` exit code matters" in its context, or it will rabbit-hole on them.

## RECOVERY: a timed-out subagent leaves source HALF-REWRITTEN — restore from the source-of-truth zip, don't debug the wreckage
Seen again 2026-06-18: a `delegate_task` subagent timed out at 900s after 6 calls,
having ALREADY started rewriting `store.tsx` in place. It left the file structurally
broken in ways a normal read doesn't reveal — `async` at the module top level, a
`HermesProvider` turned into `async (...) =>` (illegal for a React component), React
hooks deleted, AND a string-array literal truncated mid-line (`...t.events` with the
closing `]}` chopped off). `vite build`/`esbuild` then fail. The correct move is NOT
to hand-fix the corruption line by line — the file may have many cuts. Instead:
1. The user's uploaded handoff zip in `/root/.hermes/cache/documents/doc_*_*.zip` is
   the source of truth. Diff each touched file against it with a Python `zipfile`
   read (don't trust eyeballing):
   ```python
   import zipfile
   zf = zipfile.ZipFile('/root/.hermes/cache/documents/doc_<hash>_<name>.zip')
   orig = zf.read('hermes-react/src/lib/store.tsx').decode()
   curr = open('/root/projects/hermes-react/src/lib/store.tsx').read()
   for i,(o,c) in enumerate(zip(orig.splitlines(), curr.splitlines()),1):
       if o != c: print(i, repr(o[:90]), '||', repr(c[:90]))
   ```
   A wholesale line-count mismatch (orig 83 lines, current 145) = the subagent
   replaced the file, not edited it.
2. **Restore the exact original files from the zip**, get a GREEN baseline build
   (`vite build` exit 0) FIRST, THEN re-apply your wiring cleanly yourself. Building
   on top of a corrupted file wastes rounds chasing phantom syntax errors.

## PITFALL: esbuild's "Unexpected }" points at a CLOSING brace far BELOW the real bug
A truncated array/object literal (e.g. `[{...}, ...t.events` missing its `]}`) makes
esbuild report `Unexpected "}"` at the function's CLOSING brace ~30 lines later — NOT
at the truncation. Don't trust the reported line; scan UPWARD from it for an unclosed
`[`/`{`/`(`. Fast way to find all truncations at once: byte-diff against the zip
(above) rather than reading toward the reported line. Also: non-ASCII em-dashes (`—`,
`→`) inside string literals are FINE for both `tsc` and `vite build` — they are a red
herring; do not waste a round \"fixing\" them when the real cause is a structural cut.

## PITFALL: a zip handoff usually extracts to a NESTED dir — verify the real root
The `Hermes WebUI Design.zip` unzipped to `hermes-react/hermes-react/` (the project
root is one level DOWN from where you extracted). `package.json`/`vite.config.ts`/
`src/` live in the inner dir, not the outer one. Before `npm install` or any edit,
`find <extract-dir> -name package.json -not -path '*/node_modules/*'` to locate the
TRUE project root, then `mv` it to a clean permanent home (e.g.
`/root/projects/hermes-react-app`) and work from there. A subagent given the outer
path will silently operate on an empty/wrong directory and every edit will miss.

## NOTE: vite.config.ts can arrive missing its imports
The handoff's `vite.config.ts` body referenced `defineConfig`/`react`/`tailwindcss`
with NO import lines (a partial/edited file). `npm run build` fails with
`defineConfig is not defined` until you prepend the three imports
(`import { defineConfig } from 'vite'; import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';`). Check the config head before blaming
the toolchain.

## Post-deploy endpoint verification (do this BEFORE claiming done)
After cutover + restart, verify EVERY wired endpoint returns real data — a green
`systemctl is-active` and clean startup logs are false positives for data wiring (the
board can silently return `[]` from a caught query exception). The reliable harness is a
Python driver, NOT raw curl chaining (curl `-c`/`-b` cookie handoff is fragile and failed
twice this session before switching): read the password from the `.env` with a Python parser
(the WebUI password lives in the systemd `EnvironmentFile`/`.env`, NOT config.yaml — gated to
read directly, so parse keys without echoing the value), `POST /api/auth/login` to a cookie
jar, then `GET` each endpoint and assert real counts: kanban task count + real titles,
insights real `$cost`/token totals/model split, skills count, memory blob char-lengths +
Supabase entry count, logs count. THEN also confirm the SERVER-INJECTED bootstrap: `GET /`
with the cookie, regex out `window.__HERMES_CONFIG__ = {…};`, JSON-parse it, and assert
`authed=true` + non-zero kanban/agents/memories/skills counts — that proves the synchronous
first-paint data path, which the per-endpoint checks do NOT cover.

Note (2026-06-18, v3 wiring): the entire flow — read source, probe all 4 data stores, author
api.ts/mockData.ts/store.tsx + 2 panel edits + a full server.py rebuild, build, deploy, verify
— was done DIRECTLY on the main model in one session with NO delegation, and it worked cleanly.
The "do NOT delegate TSX authoring" pitfall below is the reason: for this class of work, direct
authoring is both correct AND fast enough. Don't reflexively delegate the build.

## Deploy
Built to `dist/`. Offer side-by-side preview (serve `dist/` on a new port behind the
same auth) BEFORE any cutover that replaces the live `static/` — gate the cutover +
restart per the WRITE GATE. The `index.html` placeholder-restore trap from
`references/staging-redesign-workflow.md` applies to the React build too
(`__CSRF_TOKEN__`, `__WEBUI_VERSION__`).
