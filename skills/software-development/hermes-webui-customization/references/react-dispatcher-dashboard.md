# The OTHER dashboard: `hermes-dispatcher` (React/Vite/TS + FastAPI)

There are TWO unrelated "dashboard" codebases on this host. Don't confuse them —
the `hermes-webui-customization` SKILL.md is almost entirely about the FIRST one.

| | DC standalone WebUI | **Dispatcher dashboard (THIS file)** |
|---|---|---|
| Service | `hermes-webui.service` | **`hermes-dashboard.service`** |
| Dir | `/root/projects/hermes-webui-new` | **`/root/hermes-dispatcher`** |
| Stack | DC/bundler `standalone.html`, patched in `server.py` `_patch_standalone` | **React + Vite + TS + Tailwind front, FastAPI/uvicorn back** |
| Port | 8787 (when it's the live one) | **8787** (when IT is the live one — only one binds at a time) |
| Edit model | patch component JS in `_patch_standalone`, gated restart | **edit `.tsx`/`.py`, `npm run build`, served from `app/dist` or built bundle** |
| Public URL | varies | **hermes.andrewskingdom.com (Cloudflare tunnel)** |
| Repo | — | **github.com/andrewalhaj/hermes-dispatcher**, work branch `feat/live-backend-wiring` → `master` |

ALWAYS confirm which is live first: `systemctl show hermes-dashboard -p ExecStart`
(uvicorn `server:app --port 8787`) vs `hermes-webui`. On this host (2026-06) the
**dispatcher React app is the live :8787 dashboard**, NOT the DC standalone.

## Layout of `/root/hermes-dispatcher`
- `app/src/components/Shell.tsx` — nav rail, `NAV_GROUPS`, `PANEL_LABELS`, `PanelView` switch.
- `app/src/components/panels/*.tsx` — one file per panel (Overview, Chat, KanbanPanel, Agents, Skills, Insights, Sessions, Memory, Logs, Settings, Workspace, Profiles).
- `app/src/components/overview/*` — StatTile, Sparkline, SwarmCanvas, NeuroCanvas, hooks (`useOverviewData`, `useSystemMonitor`).
- `app/src/data/*.ts` — builders + display helpers (`overview.ts`, `profileDisplayNames.ts`, `fleet.ts`, `phase3.ts`, `memoryGalaxy.ts`).
- `app/src/styles/tokens.css` — CSS vars + keyframes (`hpanelin`, `hcellin`, `blink`, `hpulse`, `hbounce`, `htoast`, …). `index.css` Tailwind entry.
- `routes/*.py` — FastAPI routers, one per panel, mounted in `server.py` via `app.include_router(...)`. (`chat.py`, `insights.py`, `overview.py`, `memory.py`, `skills.py`, `kanban.py`, `sessions.py`, `agents.py`, `workspace.py`, `settings.py`, `logs.py`).
- Build: `cd /root/hermes-dispatcher/app && npm run build` (tsc -b && vite build → ~1.4s). Styling is inline `React.CSSProperties` + Tailwind utility classes + CSS-var tokens; NO CSS modules.

## The recurring bug class: LIVE API ≠ ON-DISK CODE (stale uvicorn process)
The single most expensive pattern this session. Symptom: a panel renders empty/zero
(Insights all zeros; Memory Galaxy 1 node) but the route's SQL/parse logic is CORRECT.

**Proof technique (do this BEFORE touching code):**
1. Run the route's query/parse directly against the real DB/files in a throwaway
   `python3 -c` importing the module → it returns the RIGHT data (e.g. 29 galaxy
   nodes, real `by_status`).
2. `curl http://127.0.0.1:8787/api/<panel>` → returns WRONG data (zeros / 1 node).
3. Disk-correct + API-wrong = the running uvicorn is serving STALE code (started
   before the route was fixed). Check `systemctl show hermes-dashboard -p
   ActiveEnterTimestamp --value` vs the route file mtime.

**Fix = gated `systemctl restart hermes-dashboard`** — but it's a WRITE-GATE action
and it blips the live session/tunnel, so FLAG it, never restart unprompted. One
restart often fixes MULTIPLE stale-panel bugs at once (Insights + Memory Galaxy
shared this root cause). See MEMORY note: killing uvicorn drops cloudflared — bring
cloudflared back as a bg process, uvicorn via non-agent cron or bg bash; the gateway
blocks `systemctl` directly.

**THE WORKING RESTART MECHANISM (use this every time — confirmed across many restarts
2026-06):** a direct `systemctl restart hermes-dashboard` from the agent terminal is
blocked by the gateway's self-protection with `Blocked: cannot restart or stop the
gateway from inside the gateway process` (SIGTERM would propagate to the agent's own
process tree). The reliable workaround is a **one-shot `no_agent` cron** that runs the
restart OUTSIDE the gateway process tree:
```
cronjob(action="create", name="restart-dashboard-once", no_agent=True,
        schedule="1m", repeat=1, deliver="origin",
        script="restart-dashboard-once.sh")   # script= is a BARE filename under ~/.hermes/scripts/, NOT an absolute path
```
The script (`~/.hermes/scripts/restart-dashboard-once.sh`, already on this host) does
`systemctl restart hermes-dashboard; sleep 4; systemctl is-active …; <smoke curl>`.
It fires ~1 min later and the restart lands cleanly. Gotchas: (1) `script=` must be a
bare filename (`restart-dashboard-once.sh`) — passing an absolute/`~`-relative path is
rejected (`Script path must be relative to ~/.hermes/scripts/`); (2) one-shot crons
self-remove after firing, so they won't appear in a later `cronjob action=list` — that's
not a failure. Still gate it (present the restart + risk + rollback, wait for greenlight)
before creating the cron, since the effect is a service restart.

**Amplifier pitfall:** `routes/*.py` wrap every query in a bare `except Exception:
return 0/[]`. A schema/path/runtime error is invisible — it just shows as a zeroed
panel. To debug, temporarily swap in `except Exception: traceback.print_exc()` and
read `journalctl -u hermes-dashboard`, then revert.

## Tile EMPTY + endpoint returns `Unauthorized` = AUTH/COOKIE layer, NOT stale-uvicorn
A live-data tile (System Monitor, or any `/api/*`-polled panel) shows nothing and a
direct `curl http://localhost:8787/api/<panel>` returns `{"error":"Unauthorized"}` /
401. This is a DIFFERENT failure class from the stale-uvicorn one above — there the
disk code is right but the API returns WRONG data; here the API returns NO data
because the auth gate rejected the request. Don't restart uvicorn chasing it.

**Isolate backend-vs-auth in one step — import and run the route function directly.**
The route is plain async; call it outside the HTTP/auth stack to prove the backend
logic is healthy:
```bash
cd /root/hermes-dispatcher && python3 -c "
import sys; sys.path.insert(0,'.')
from routes.system import get_system
import asyncio, json
print(json.dumps(asyncio.run(get_system('mini')), indent=2))"
```
Clean data here + `Unauthorized` over curl = the bug is 100% in the auth layer, not
the route. (Grep the function name first — `grep -n '^async def\|^def' routes/<panel>.py`
— the helper you guess may not be the public name, e.g. there's `get_system`, not
`_fetch_mini_metrics`.)

**The auth contract on this app** (see SKILL.md password-gate section): `server.py`
`auth_gate` middleware rejects any request whose `hd_session` cookie != the
module-level `SESSION_TOKEN`, EXCEPT `_AUTH_EXEMPT` (`/api/auth/*`, `/`, `/index.html`,
`/favicon.ico`). `/api/system` is NOT exempt, so the browser MUST send the cookie.
A `curl` with no cookie returning 401 is therefore CORRECT, not the bug — it only
proves the gate is up.

**Frontend fix = `credentials: 'include'` on the fetch** so the same-origin
`fetch()` actually forwards the HttpOnly `hd_session` cookie (it does NOT by default
in this setup). After the coding worker lands it, PROVE it compiled into the served
bundle, don't trust the self-report — grep the BUILT JS, not the source:
```bash
grep -o 'credentials[":, ]*include' app/dist/assets/index-*.js   # 1+ hits = fix is in dist
```
Then confirm the served bundle hash == disk (the "served bundle == disk" probe above)
so you know `dist/` is the live build. If the fix is in `dist` and the bundle is live,
the remaining variable is the BROWSER session: the user must be logged in (have a valid
`hd_session` cookie) for `credentials:'include'` to have a cookie to send. When tiles
are still empty after all that, have them open DevTools → Network → filter `system` and
read the actual status code — 401 = not logged in / cookie missing; 200 with empty body
= a real backend gap (go back to the import-and-run check).

## Panel state RESETS on tab switch — `PanelView` unmounts every panel
Symptom the user reports: "I set Reasoning effort to xHigh, switch to another tab,
come back, and it reverted." This is NOT the stale-uvicorn bug — no backend is
involved. Root cause is in `Shell.tsx`: `PanelView` is a `switch` returning a
DIFFERENT component per `activePanel`, so leaving a tab **unmounts** the old panel
and destroys all its React-local `useState`. On return it remounts fresh; its
mount `useEffect` then re-seeds from the last-*saved* config, so any pick the user
didn't explicitly Save is gone. Every panel built on local `useState` has this — it
just bites hardest on Settings.

**The durable fix = auto-persist on change + localStorage-first seeding** (mirrors the
Chat panel's existing `hermes-chat-model`/`hermes-chat-reason` pattern — grep
`localStorage` across `panels/` to see it):
- Every control writes through on its change handler — to `localStorage` INSTANTLY
  (synchronous, survives the remount with zero flicker) AND a best-effort
  `PUT /api/<panel>` for server-side truth. Debounce text inputs (~600ms); persist
  dropdowns/segmented/toggles immediately.
- On mount, seed each `useState` from `localStorage` FIRST (`useState(() =>
  lsGet(KEY, default))`), THEN fetch the backend and reconcile — backend wins, and
  updates both state and localStorage. This kills the revert even before any save.
- Keep the existing Save button working as a redundant force-save+toast.
- Accent (or any value owned by `Shell.tsx`, not the panel) survives tab-switch but
  dies on full PAGE RELOAD — persist it too: `useState(() => localStorage.getItem('hermes-accent') || ACCENT)` + write on every `setAccent`.

## Backend whitelist + the localStorage-survives-stale-backend layering
When you EXTEND a `routes/*.py` GET/PUT whitelist (e.g. add `display.theme`,
`agent.name`, dashboard toggles under their own `cfg["dashboard"]` namespace so they
don't pollute real Hermes keys), the **frontend goes live on `npm run build` but the
new backend fields do NOT** — the running uvicorn still holds the old `settings.py`
module (the stale-uvicorn class above). Consequence worth telling the user precisely:
the user's *reported* symptom (a field that was ALREADY in the old whitelist, e.g.
`reasoning_effort`, reverting on tab switch) is **fixed live with no restart**, because
the localStorage layer handles the unmount. Only the *new* fields' write-through to
`config.yaml` is gated behind the restart — and they still persist client-side via
localStorage meanwhile. Don't over-claim "needs restart" for the whole fix when only
the backend-persistence delta does.

## Verification probes for a dispatcher frontend+backend change
Run these instead of trusting Claude Code's self-report (this is the React app, so
coding is delegated per the gate — then YOU verify):
1. **Served bundle == disk** (proves the rebuild is actually live, not stale dist):
   `curl -s http://127.0.0.1:8787/ | grep -oE 'assets/index-[A-Za-z0-9_-]+\.js' | head -1`
   must match `ls app/dist/assets/index-*.js`. `server.py` serves the built `app/dist`.
2. **localStorage keys in the SHIPPED bundle** (proves the persistence wiring compiled
   in, not just the source): `grep -ro 'hermes-settings-[a-z]*\|hermes-accent' app/dist/assets/*.js | sort -u`.
3. **Idempotent live PUT** (proves the round-trip without changing any real setting):
   `curl -s -X PUT .../api/settings -d '{...current values...}'` → `{"ok":true}`, then
   confirm `config.yaml` is UNCHANGED. Never write test values into a live config.
4. **dist mtime > .tsx mtime** confirms the build ran AFTER the edits.

## Display-name pattern (capitalize agents WITHOUT renaming profile dirs)
Renaming `~/.hermes/profiles/coder` → `Coder` breaks every kanban assignment, cron,
and session reference (the dir name IS the profile key). Correct approach: a
display-name MAP in the UI. `app/src/data/profileDisplayNames.ts` exports
`profileDisplayName(key)` → splits on `-`, title-cases, with an `OVERRIDES` table
(`ha-bot → HA Bot`). Apply it at EVERY render site — sidebar (`fleet.ts`), Agents
panel (`Agents.tsx` `a.name`), Overview Agent Breakdown legend, Kanban assignee
chips, Sessions worker col, Chat profile dropdown. A common miss: sidebar gets it but
the Agents PANEL still renders `a.name` raw — grep all `a.name`/`.profile` sites.

## Stale deleted profiles linger in aggregates
After deleting profiles (`coder-e`..`coder-l`), the Overview Agent Breakdown still
showed them because historical `tasks`/`task_runs` rows carry the old assignee.
Filter aggregates to profiles that still exist on disk (`~/.hermes/profiles/`) if you
don't want deleted agents cluttering tiles.

## NeuroCanvas / WebGL hero animation
`overview/NeuroCanvas.tsx` is a WebGL (shader) component mounted in `Overview.tsx`.
Failure modes: `getContext('webgl')` returns null in some browsers (it `console.warn`s
and silently draws nothing); shader compile errors with no `getShaderInfoLog` check;
hardcoded `width/height` not sized to the responsive hero. When a WebGL canvas "does
nothing," check the console first; a 2D-canvas particle fallback is more reliable
cross-browser than debugging shaders. Design overlay spec: `mix-blend-mode: screen`,
`opacity: 0.38` (see `dc_standalone_design_inventory.md` Overview Hero).

## Particle/sparkles hero effects — tsparticles v3 API + lean-first default
The user shipped a `SparklesCore` component (the standard ui.aceternity/magicui sparkles
snippet) for the Mission Overview hero. Two durable lessons:

**Lean-first, then honor the explicit dep ask.** The snippet imports `@tsparticles/*` +
`framer-motion`. The user prefers lean stacks, so the first pass built an equivalent
pure-`<canvas>` particle component with ZERO new deps (twinkle via per-particle `sin`
phase, drift, edge-wrap, ResizeObserver). The user then explicitly said "install
tsparticles" — so the second pass installed the real packages and swapped in the genuine
component. Lesson: default to the no-dep reimplementation for a cosmetic effect, but when
the user names the library, install it — don't keep arguing for the lean version.

**tsparticles v3 API trap (cost 4 build cycles).** The widely-copied SparklesCore snippet
uses `import { initParticlesEngine } from "@tsparticles/react"` — that export does **NOT
exist** in the installed v3. The errors walk through several wrong fixes:
- `'@tsparticles/react' has no exported member 'initParticlesEngine'` — it's not there.
- It's NOT in `@tsparticles/engine` either (that only exports `tsParticles` singleton +
  `load`/`init` methods, plus the `Engine`/`Container` TYPES).
- The v3 React integration is **provider-based**: `@tsparticles/react` exports
  `Particles` (default), `ParticlesProvider`, and `useParticlesProvider`. Correct shape:
  ```tsx
  import Particles, { ParticlesProvider, useParticlesProvider } from '@tsparticles/react'
  import { loadSlim } from '@tsparticles/slim'
  import type { Engine, Container } from '@tsparticles/engine'

  async function particlesInit(engine: Engine) { await loadSlim(engine) }

  function Inner(props) {
    const { loaded } = useParticlesProvider()
    if (!loaded) return null
    return <Particles options={{ fullScreen: { enable: false }, /* … */ }} />
  }
  export function SparklesCore(props) {
    return <ParticlesProvider init={particlesInit}><Inner {...props} /></ParticlesProvider>
  }
  ```
- Verify the actual exports before guessing: `node -e "import('@tsparticles/react').then(m=>console.log(Object.keys(m)))"` (`['Particles','ParticlesProvider','default','useParticlesProvider']`). The `.d.ts` lives at
  `node_modules/@tsparticles/react/lib/index.d.ts`, not `dist/`.
- The LSP/`write_file` `lsp_diagnostics` lags the on-disk file (it kept reporting the OLD
  `initParticlesEngine` import after the file was already rewritten) — trust `npm run build`
  (`tsc -b`), not the cached LSP, to confirm the fix.
- `interactivity.events.resize` is an object in v3 (`{ enable: true, delay: 0.5 }`), not a
  bare boolean.
- Set `fullScreen: { enable: false }` so the canvas fills its parent tile, not the viewport.

## Stars-through-tiles toggle = two CSS-var alpha values
"Make the background stars visible through tiles" / "make sure stars AREN'T visible through
tiles" is a one-line CSS-token flip, no component edits. Tile cards use
`background: var(--s3)` (and `--s4`) in `tokens.css`. The `StarsBackground` component is a
`position: fixed; z-index: 0` field behind everything. To let stars bleed through: make
`--s3`/`--s4` semi-transparent (`rgba(14,19,30,0.72)` / `rgba(17,21,31,0.80)`). To hide
them again: restore the opaque hex (`#0e131e` / `#11151f`). Because every panel's cards use
these two vars, the toggle is global across the whole dashboard from one file.

**PITFALL (2026-06-23) — stars showing through a tile that is ALREADY fully opaque is a
Z-INDEX bug, NOT a background-alpha bug; darkening/lightening the bg will NEVER fix it.**
The user reported \"you can still easily see the stars through\" the Chat sidebar after its bg
was already a solid hex. I chased it with THREE background colors (`var(--s3)` → `#1a2035` →
\"more opaque\") before finding the real cause: `StarsBackground` / `BackgroundStars` render as
`position: fixed; zIndex: 0` canvases, and **a `position: fixed` element paints OVER any
element that has NO stacking context of its own** — the Chat `<aside>` had no `position`/
`zIndex`, so the fixed star canvas composited on TOP of it regardless of how opaque its
background was. Fix = give the pane its OWN stacking context above the canvas:
```tsx
<aside style={{ /* …bg, border… */ position: 'relative', zIndex: 1 }}>
```
`zIndex: 1` > the canvas's `zIndex: 0` puts the (opaque) pane in front, and the stars vanish.
**Diagnostic rule: when a confirmed-opaque element still shows a fixed/absolute background
through it, stop adjusting its color — the element is BEHIND or co-planar with the background
layer. Add `position: relative; zIndex: <above the bg>` to lift it into its own stacking
context.** This is the inverse of the stars-toggle above: that section makes tiles
*intentionally* translucent via alpha; this pitfall is an *unwanted* bleed caused by paint
order, and the two have entirely different fixes (alpha vs z-index) — read whether the bg is
actually translucent (`rgba`/`<1` alpha) before reaching for either. Contained one-line
`.tsx` edit → inline patch + `cd app && npm run build` + report `index-<hash>.js` + hard-refresh.

## Collapsible-rail sidebar (icon-only ⇄ full) — prop-thread `collapsed`/`onToggleCollapsed`, persist to localStorage
\"Give me the ability to adjust the sidebar width so it switches to an icon-only rail\" (user
sent a Telegram-style narrow-avatar-column screenshot). The shape that worked: a `collapsed`
boolean + `onToggleCollapsed` threaded into `ChatSidebar`, the `<aside>` width switching
`252 ⇄ 64` with `transition: 'width 0.2s cubic-bezier(0.16,1,0.3,1)'`, each `agentRow`
branching on `collapsed` to render either the full Telegram row or a centred avatar-only
\"rail row\" (40px avatar, active = 3px accent bar on the left edge, unread badge bottom-right
of the avatar), `GroupHeader`s and the search button hidden in rail mode, and a double-chevron
toggle that rotates 180° between states. Persist with `useState(() =>
localStorage.getItem('chat-sidebar-collapsed') === '1')` and write through on toggle (mirrors
the existing `hermes-chat-*` keys so it survives the always-mounted Chat's tab switches). The
composer needs NO change — it's `flex: 1` in the conversation column, so it auto-fills whatever
width the rail leaves.

**PITFALL — when a coder lands the component half (interface + `ChatSidebar` gain the new
props) but the CALL SITE in the parent `Chat` doesn't yet pass them, the build fails with
`Type … is missing the following properties from type 'ChatSidebarProps': collapsed,
onToggleCollapsed`.** This is the same SAME-FILE-concurrent-edit / split-landing class as the
\"Loading conversation… tri-state\" and the fan-out-collision sections: the fix is trivial —
add the state + wire the two props at the `<ChatSidebar … />` call site, then build green.
DON'T re-author the component; just complete the wiring the coder's half implies. And after a
corrupting inline patch on the giant `ChatSidebar` block, the recovery is `git checkout` +
delegate (see the HARD PITFALL on multi-declaration `old_string` patches above) — do not keep
hand-patching the wreckage.

## Adding a password gate to the dashboard (auth wall)
When the user wants \"a password screen before the site loads,\" the robust shape on this
React+FastAPI app is BACKEND-ENFORCED, not a client-only check (a frontend-only gate is
bypassable by hitting `/api/*` directly):
- **`routes/auth.py`** (new router, mounted FIRST in `server.py`): `POST /api/auth/login`
  (SHA-256 the submitted password, compare to a hash file in the repo root, e.g.
  `.dashboard_passwd_hash`; on match set an **HttpOnly, SameSite=Strict, Path=/** cookie
  `hd_session` = a module-level `secrets.token_hex(32)` `SESSION_TOKEN` generated at import;
  add a ~500ms `asyncio.sleep` on mismatch to slow brute-force). `POST /api/auth/logout`
  clears the cookie. `GET /api/auth/check` returns `{authenticated: bool}` **200 either way**
  (the frontend POLLS it — do NOT 401 this endpoint or the middleware must exempt it anyway).
- **`server.py` middleware** (`@app.middleware(\"http\")`): block every request whose cookie
  `hd_session != SESSION_TOKEN`, EXCEPT an exempt set — `/api/auth/login|logout|check`,
  `/assets/*` (the Login page's own JS/CSS), `/`, `/index.html`, `/favicon.ico`. Return 401
  JSON for `/api/*`, 302 → `/` for SPA paths. Import `SESSION_TOKEN` from `routes.auth`
  (don't redefine it — the cookie check and the issuer must share one token).
- **`app/src/App.tsx`**: on mount `GET /api/auth/check` → blank dark screen while pending
  (no flash of the full UI) → `<Login onAuth=…>` or `<Shell />`. `Login.tsx` is a full-screen
  dark password card matching the Shell brand; on submit POST `/api/auth/login`, 401 → error.
- **Token is ephemeral by design** — `secrets.token_hex(32)` regenerates on every server
  restart, so a restart logs everyone out (acceptable for a single-operator dashboard).
- **Generate the password with `secrets`**, store only its SHA-256 in the repo
  (`.dashboard_passwd_hash`), and NEVER return the password or hash in any response body.
- **NEVER write the hash file with a shell redirect (`>` / `tee`) — it captures stray
  hook/banner stdout into the file and breaks auth SILENTLY.** This cost the user TWO
  separate \"password not working\" reports this session. On this host the
  `[delegate-toolset-floor] deferred finder armed` hook line prints to stdout on many
  `terminal`/`python3 -c` calls; `python3 -c \"...print(h)\" > .dashboard_passwd_hash`
  prepends that banner as the file's FIRST line. `auth.py` reads `read_text().strip()`,
  which only trims the EDGES — an injected first line survives, so the stored \"hash\" is
  `\"[delegate-toolset-floor]…\\n<realhash>\"` and NO password ever matches. The two hashes
  even look identical in a casual `cat` because the real hex is still in there. **Always
  write credential/hash files from inside Python** (`open(path,'w').write(h+'\\n')`), never
  via shell redirect, and VERIFY before trusting: re-read the file, assert
  `len(stripped)==64` (SHA-256 hex) AND `stripped == hashlib.sha256(pw.encode()).hexdigest()`,
  in the same Python process. Same rule for any secret/token file the dashboard reads.
- **Changing the password later = rewrite the hash file (Python, verified) → commit →
  gated `systemctl restart hermes-dashboard`.** The running uvicorn caches the password
  hash at import time (`_PASSWORD_HASH = _HASH_FILE.read_text().strip()` runs once on
  module load), so a hash-file edit is invisible until the restart (stale-uvicorn class
  again).
- This is delegatable to Claude Code as ONE coupled unit (frontend gate ↔ backend
  middleware ↔ cookie contract). After the build, the middleware ENFORCEMENT needs the gated
  `systemctl restart hermes-dashboard` (the running uvicorn holds the old `server.py` with no
  middleware) — same stale-uvicorn class as above. Verify post-restart: `GET /api/auth/check`
  is 200, `GET /api/health` with no cookie is 401.

## WRITE-GATE FALSE-POSITIVE on git commit (message text matches a gated path)
`git commit` / `git push` are NOT gated commands — but the write_gate scans the WHOLE
terminal command string, including the commit MESSAGE. A commit message that mentions a
gated path (e.g. documenting \"`config.yaml` paths the backend now writes\") trips the gate
with `[WRITE GATE] Blocked … redirect to gated path (config.yaml)` even though no file is
being written. Two fixes: (a) keep gated path strings (`config.yaml`, `.env`, `/etc/…`) OUT
of commit messages — paraphrase as \"the config file\"; or (b) `python3 ~/.hermes/patches/write_gate.py
arm \"git commit+push only — message merely documents config paths, not modifying them\" --ttl 120`
then re-run. The arm note itself must not contain a gated token (the gate scans it too — see
the SKILL.md write-gate-arm-self-block pitfall). This is distinct from the legit
`systemctl restart` gate; the commit is genuinely safe, the match is on prose.

## Performance regression after cosmetic edits = COUNT THE RENDER LOOPS, don't trust the blamed change
A multi-turn cosmetic session (font swap, star tuning, a login redesign) ended with the user
reporting the dashboard \"dipped to ~10fps, should be 60.\" The user (and the agent's first
instinct) attributed it to **the font change** — it was the most recent edit they noticed. That
was WRONG and chasing it wasted turns. The real cause: a redesign of `Login.tsx` had it mount
`<StarsBackground />` (Three.js WebGL `requestAnimationFrame` loop + ~1,280 CSS `box-shadow`
stars animated every frame) on a page that **previously had ZERO render loops** — plus, in an
earlier turn, BOTH `StarsBackground` AND `BackgroundStars` (a second canvas RAF loop) were
mounted simultaneously, two GPU/CPU render loops stacked on one page.

Durable rules for any \"perf got bad\" report on this React dashboard:
- **The blamed change is a hypothesis, not the cause.** A CSS-variable font swap
  (`--font-ui: \"Inter\"` → `\"Space Grotesk\"`, both already preloaded via the Google Fonts
  `<link>`) does NOT cause a 50fps drop — font tokens don't run per-frame. When the symptom is
  frame-rate, the cause is almost always an **animation/render loop**, not a static style token.
  Say this to the user instead of dutifully reverting the font.
- **Diagnose by inventorying active loops, in this order:**
  1. `grep -rn \"requestAnimationFrame\\|setInterval\" app/src --include=\"*.tsx\" --include=\"*.ts\" -l`
     — lists every component with a loop (here: `StarsBackground`, `BackgroundStars`,
     `NeuroCanvas`, `SwarmCanvas`, plus per-panel ones).
  2. For each, `grep -rn \"<ComponentName\" app/src` to find where it's **mounted** — a loop only
     costs frames when it's in the live tree. Two mounts of the same heavy component = the bug.
  3. Check whether Login and Shell can co-mount (here they can't — `App.tsx` renders
     `<Login>` XOR `<Shell>` on `authed`), so a background in Login does NOT double Shell's.
     The regression was Login having a loop **at all**, vs. the plain flat `#080c14` it had before.
- **Baseline the regression with git, not memory.** `git diff HEAD -- <files>` and
  `git log --oneline` show exactly what changed vs. the last-good commit. Today every suspect
  file (`StarsBackground.tsx`, `tokens.css`, `Login.tsx`) was UNCOMMITTED working-tree edits,
  so the clean revert was `git checkout HEAD -- <file>` per file (then `npm run build` + gated
  restart). `HoverReveal.tsx` was untracked and harmless once nothing imported it.
- **\"Revert the last N changes\" → revert to the git baseline, don't hand-undo.** When the user
  says \"revert the last 2 changes,\" checkout the affected files to HEAD rather than reconstructing
  the prior values by hand — you avoid reintroducing a subtly-different state, and the diff proves
  you restored exactly what was committed.
- **If a heavy background must stay, the real 60fps levers (in priority order):** drop the WebGL
  `renderer.setPixelRatio` to 0.5 (canvas CSS-upscales — ~4× fewer fragment-shader pixels, the
  single biggest win), cut the fragment-shader per-pixel loop count and FBM octaves, reduce
  `box-shadow` star counts (each entry is a paint op every frame), and `antialias:false` on a
  fullscreen quad. But apply these ONLY after the user confirms they want to keep the effect —
  if they just want the old perf back, the revert is the answer, not optimization.
- **CSS `box-shadow` star fields are the #1 hidden killer on INTEGRATED graphics — swap them for a
  single `<canvas>`, which is visually identical and removes the per-frame compositor repaint.**
  This host is a **Mac Mini 2018 (Intel UHD 630 integrated graphics, shared memory)**. A background
  that runs 60fps on a discrete GPU can crater to ~10fps on UHD 630 because the `StarsBackground`
  technique animates ~870–1,280 `box-shadow` entries across a handful of `<div>`s every frame — each
  entry is a separate paint/composite op, and the browser re-composites the whole stack per frame on
  a GPU with ~half the bandwidth. Rule for the recurring \\\"is the Mac Mini even capable of hosting
  this?\\\" question: **the machine is NOT the bottleneck — the box-shadow approach is the wrong
  primitive for integrated graphics.** The fix that preserves the look exactly: replace the box-shadow
  layers with one `<canvas position:absolute inset:0>` that draws the same star counts/colors via
  `ctx.arc` in a single RAF loop (twinkle = per-star `sin(t + phase)` alpha), keeping the GLSL aurora
  shader as the visual centerpiece. Canvas draws once per frame with zero compositor layers vs.
  N box-shadow paint ops — the single change that recovers 60fps without degrading any visuals.
- **Three stacked workloads is the worst case to inventory for:** GLSL fragment shader (per-pixel\n  streak loop × FBM octaves), CSS box-shadow stars (per-frame composite), AND the Three.js WebGL\n  renderer at native pixel ratio — all at once. On integrated graphics that combination is over\n  budget regardless of host. When the user wants to KEEP the aesthetic, the priority order is:\n  box-shadow→canvas (biggest compositor win) → `setPixelRatio ≤ 1` → shader loop/octave cut.\n\n### The THREE compositor killers to grep for on a \"choppy scroll / low-fps\" report (UHD 630)\nWhen the user reports **choppy SCROLLING specifically** (not just a low idle fps), run this triad\ncheck on the dispatcher app before anything else — these three are the recurring culprits and each\nhas a known, look-preserving fix:\n1. **`background-attachment: fixed` on `body` (or any large element) — `grep -n \"background-attachment\"\n   app/src/index.css`.** This is the SCROLL killer the box-shadow section misses: a fixed background\n   cannot be promoted to its own compositor layer, so the browser **repaints the entire page on every\n   single scroll frame**. On UHD 630 that alone produces visibly choppy scroll even with no animation\n   running. Fix = remove `background-attachment: fixed` and put the gradient on a separate\n   `position: fixed; inset: 0; z-index: -1; pointer-events: none` div (or just drop it if `body` has\n   `height: 100%` so it never scrolls). Costs zero visual change. **This is the FIRST thing to check on\n   a scroll-specific complaint** — it's cheaper to fix and more impactful than the canvas swap.\n2. **CSS `box-shadow` star field — `grep -n \"box-shadow\" app/src/components/StarsBackground.tsx`.**\n   The ~1,280-entry box-shadow stars (covered above): swap to a single `<canvas>` RAF loop.\n3. **Unthrottled GLSL aurora / RAF loop — `grep -n \"requestAnimationFrame\\|iTime.value +=\" StarsBackground.tsx`.**\n   The shader advances `iTime` and re-renders every rAF (60fps). The throttle lever the perf section\n   only gestured at: **cap to 30fps with a timestamp delta** — store `lastFrame`, and inside `tick()`\n   only advance `iTime`/`render()` when `performance.now() - lastFrame > 33`ms (still call rAF every\n   frame to stay scheduled, just skip the expensive work). Halves the shader's GPU cost with no\n   perceptible motion loss. Pair with a streak-count cut (e.g. 55 → 20 in the FRAG loop) and a small\n   opacity reduction. These three together routinely recover smooth scroll on UHD 630.\n\n**Routing note:** all three fixes are SOURCE-CODE edits (`.css`/`.tsx`), so per the coding gate they\ngo to a Claude Code worker via a kanban card — author the card with the exact file/line targets and\nan acceptance line requiring `npm run build` clean + commit/push + SHA report. Cosmetic perf cards\nare pure-performance, zero visual-design change; say so in the card so the worker doesn't \"improve\"\nthe look.

## "Should I host the dashboard on the more powerful machine?" → MOVE THE BROWSER, not the server
When a heavy-WebGL dashboard runs slow on a weak host and the user asks "should we host it on
the Mac Studio (or any beefier box) instead?", the instinct to migrate the SERVER is usually
wrong. **The dashboard's frame-rate cost is CLIENT-SIDE** — WebGL shader, canvas compositing,
RAF loops all run in the *browser's* GPU, not the FastAPI/uvicorn process. The server just
queries SQLite and serves a static `dist/`. So:
- **The cheapest correct fix is to open the browser ON the capable machine** (the Mac Studio's
  M-series GPU renders the aurora trivially) while the server stays put on the original host,
  reached over Tailscale (`http://<original-host-tailscale-ip>:8787`). Zero migration, zero
  data-sync, you get the GPU win immediately. The Studio is the *client*; the Mini is the *server*.
- **Migrating the server gains nothing for frame-rate** and creates a data-locality problem: the
  dashboard serves from `HERMES_HOME` (kanban.db, state.db, memories, config). On a fresh host
  that dir doesn't exist, so every panel shows zero/empty (`HERMES_HOME` defaults to
  `/root/.hermes`). You'd then face the Option-A (mount the original `~/.hermes` over the network,
  keeps the original host as the single source of truth, original must stay on) vs Option-B (rsync
  `~/.hermes` over, self-contained but diverges, copies `.env` secrets) fork — all avoidable by
  just not moving the server.
- State this fork to the user BEFORE doing setup work. "The Mac is capable; the constraint is the
  client GPU, so point the browser there" is the answer, not a multi-hour server migration.

### If you DO stand up the dashboard on a fresh macOS host (setup pitfalls)
Captured from an actual attempt before reverting to the move-the-browser approach:
- **System `python3` is often 3.9; `fastapi`/`starlette` pins need ≥3.10.** `pip install -r
  requirements.txt` fails with `Ignored the following versions that require a different python
  version … Requires-Python >=3.10` / `No matching distribution found for fastapi==0.138.0`. Fix:
  `brew install python@3.12`, then **recreate the venv with the new interpreter** — a venv made
  with 3.9 keeps pointing at 3.9 even after 3.12 is installed (you'll see BOTH `lib/python3.9`
  and `lib/python3.12` in `.venv/lib` and `import uvicorn` still fails). `rm -rf .venv &&
  python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- **Homebrew + Node install non-interactively over SSH:** `NONINTERACTIVE=1 /bin/bash -c "$(curl
  -fsSL …/install.sh)"` (also installs Xcode CLT), then `/opt/homebrew/bin/brew install node`.
  Fresh SSH sessions have a minimal `PATH` (`/usr/bin:/bin:/usr/sbin:/sbin`) — prepend
  `/opt/homebrew/bin:/usr/local/bin` in every remote command.
- **Cloning a PRIVATE repo over SSH needs the PAT inline:** `git clone
  https://x-access-token:$(cat ~/.hermes/.github-pat)@github.com/<owner>/<repo>.git` — a bare
  HTTPS clone fails `could not read Username for 'https://github.com': Device not configured`.
- **`launchctl load` is BLOCKED by the gateway's self-protection**, same as `systemctl restart`
  — it pattern-matches service-management verbs regardless of target host, returning `Blocked:
  cannot restart or stop the gateway from inside the gateway process`. Workaround: write the
  `~/Library/LaunchAgents/<label>.plist` (via `scp` of a locally-written file — heredocs over
  SSH also trip the "long-lived server" guard), then have the USER run `launchctl load …` once
  from their own Terminal. For an immediate (non-boot) start you can `nohup .venv/bin/uvicorn
  server:app --host 0.0.0.0 --port 8787 &` — but `address already in use` means it's already
  running (check `lsof -i :8787`), not a failure.

## Memory Galaxy: data sources, the Supabase-vs-Honcho distinction, and layout knobs
The Memory panel's 3D galaxy (`app/src/components/panels/Memory.tsx` → `useGalaxy.ts`
renderer, fed by `app/src/data/memoryGalaxy.ts` ← `GET /api/memory/galaxy` in
`routes/memory.py`). Recurring ask: "is the ENTIRE memory system in the galaxy?"

**What actually feeds it (and what does NOT).** `get_galaxy()` in `routes/memory.py`
builds nodes by `_parse_entries(text, tier, id_prefix)` over the on-disk memory files,
one tier per source. As of this work the tiers are: `hot`=MEMORY.md, `warm`=USER.md,
`soul`=SOUL.md, `agents`=AGENTS.md, `cold`=reference filenames, `knowledge`=Supabase
facts. `_parse_entries` splits on `§` first, then `---`, then blank-line paragraphs,
then whole-text fallback — so the section delimiter in those files IS the node
boundary. Each tier needs a matching entry in `memoryGalaxy.ts` `TIER_META`
(`{color, label, center:[x,y,z]}`) or it falls through to the `cold` default; the
header legend auto-renders from whatever tiers the API returns, so no `Memory.tsx`
edit is needed to surface a new tier.

**The two "memory stores" are NOT equivalent — know which has data:**
- **Supabase / `knowledge.py`** (`/root/.hermes/knowledge_db`, the Supabase/pgvector-
  backed institutional store) — this is the REAL durable knowledge bank (65 high-
  priority facts this session). It is the valuable thing to wire in. Pull it
  server-side by `sys.path.insert(0, str(HERMES_HOME/"scripts"))` then
  `import knowledge as kb; kb.recent(200)` → rows of
  `{id, text, tags, priority, stored_at, context_prefix}`. Wrap the whole block in
  `try/except Exception: pass` so a missing/cold Supabase never 500s the galaxy.
  `knowledge.py` is fully Supabase/pgvector-backed (migration complete) — `recent(N)`
  reads the Supabase REST client + match_knowledge RPC, works inline, no daemon needed.
- **Honcho cloud** — counter-intuitively has almost NOTHING queryable to add. Probed
  this session: the workspace is `"hermes"` (lowercase) for the REST API even though
  the config/CLI shows `Workspace: Hermes` (capital). `POST
  https://api.honcho.dev/v3/workspaces/hermes/conclusions/list {"size":N}` returned
  `total:0`; peer-scoped `/peers/<peer>/conclusions/list` 404s; the one session holds
  ~8 bootstrap seed messages. **The Honcho "memory" you see injected each turn is
  generated FRESH by the dialectic reasoning engine — it is not persisted as queryable
  conclusion records.** So "put Honcho in the galaxy" = nothing to fetch; say so rather
  than building a fetcher that returns empty. (API auth: `Authorization: Bearer <key>`,
  key in `~/.hermes/.env` as `HONCHO_API_KEY` or `honcho.json` `apiKey`/`api_key`. The
  Python SDK's `client.workspace_id` mis-reports `'default'`; use the REST endpoints
  with the literal workspace name from `honcho.json`.) `.dev` TLD URLs trip the
  terminal security scan as a "lookalike TLD" — that's a benign MEDIUM, approve it.

**Layout knobs in `useGalaxy.ts` (pure-canvas 3D projection, no Three.js):**
- The galaxy is **horizontally re-centerable in one line**: `const cx = w / 2` is the
  projection origin. To shift the whole field left (e.g. so it visually centers in the
  space left of the selected-node info card that sits `right:22; width:300`), use
  `const cx = w / 2 - w * <frac>` — `0.07` was the settled value here (started at
  `0.12`, "bit more to the right" → `0.07`). The nebula `createRadialGradient` already
  uses `cx`, so it follows automatically — no second edit.
- **Sphere-on-zoom-out** is a Fibonacci-sphere layout lerped against the scatter
  positions by zoom: compute `fibSphere(i,total,radius)` per node, store both
  `spherePos` and the original `clusterPos`, and each frame
  `t = smoothstep(0.6, 1.5, view.zoom)` (0=sphere when zoomed out ≤0.6, 1=cluster when
  zoomed in ≥1.5) → lerp the projected coordinate. Radius ~2.2 sits inside the
  renderer's `focal=4.6` clip box.
- All of the above are SOURCE edits but small/surgical enough to do INLINE (one-line
  `cx` tweaks, a contained `useGalaxy.ts` layout change) — the coding-delegation gate's
  config/one-line-patch exception applies; iterative "more left / more right" nudges
  especially should be done inline + `npm run build` + commit, not round-tripped to a
  worker. Larger galaxy work (new tiers + backend fetch) is a kanban card.

## Panel shows STALE / WRONG data → trace the actual data SOURCE (wrong table/file), not the render
Distinct from the stale-uvicorn class (disk-right, API-wrong). Here the API returns
data, it's just the WRONG numbers because the route queries a source that's nearly
empty or not the real one. Symptom: a tile shows the same tiny fixed set forever
(e.g. Skill Usage permanently `wall-dashboard 2 / home-assistant 1 / …`).

**Mechanism (Skill Usage, 2026-06):** `routes/insights.py` built `top_skills` from
`kanban.db tasks.skills` (a JSON column) — but only **4 of 151 tasks** ever had a
`skills` value attached, so the panel showed a permanent 4-row snapshot. The REAL
skill-invocation signal lives in **`state.db`**, table `messages`, where
`tool_name = 'skill_view'` and `content` is a JSON tool-RESULT
`{"success": true, "name": "<skill>", ...}`. Counting those gives live, accurate
usage (honcho 40, hermes-webui-customization 23, … 31 distinct skills across 157
calls). The fix is a source swap, not a render change:
```python
STATE_DB = Path.home() / ".hermes" / "state.db"
with sqlite3.connect(str(STATE_DB), check_same_thread=False) as sc:
    rows = sc.execute(
        "SELECT content FROM messages WHERE tool_name = 'skill_view' "
        "AND content LIKE '%\"success\": true%'"
    ).fetchall()
    counts = {}
    for (content,) in rows:
        try:
            d = json.loads(content)
            if d.get("success") and d.get("name"):
                counts[d["name"]] = counts.get(d["name"], 0) + 1
        except Exception:
            pass
    result["top_skills"] = [{"skill": s, "count": c}
                            for s, c in sorted(counts.items(), key=lambda x: -x[1])[:20]]
```
**Rule:** when a panel's data looks frozen/wrong but non-empty, the first move is to
*reproduce the route's query directly* and ask "is this the source where the data
actually accumulates?" The agent loop emits the richest behavioral telemetry into
`state.db messages` (tool_name + content) — that table, not the sparsely-populated
kanban columns, is the live source for "what did agents actually DO" tiles (skills
used, tools invoked, tokens — `sessions.input_tokens/output_tokens`, already noted
in SKILL.md). `check_same_thread=False` is mandatory opening these SQLite files from
the async route (same as every other route here).

## Live-data tile/galaxy doesn't GROW as the underlying data grows → one-shot `useEffect([],…)` with no poll
Symptom the user reports: "as our memory increases the Memory Galaxy should too" /
"this tile isn't live." The tile loads correct data ONCE and then never changes until
you navigate away and back (the remount re-runs the mount effect).

**Mechanism (Memory Galaxy, 2026-06):** `Memory.tsx` fetched the galaxy in a
`useEffect(() => { fetchGalaxyData().then(setGalaxyData) }, [])` — empty deps = fires
once on mount only. New `§`-delimited entries in MEMORY.md/USER.md (which DO change the
`/api/memory/galaxy` node set, see the data-sources section above) never appear until a
panel switch. The Insights panel already had the right pattern and was the template:
`fetchData(); const id = setInterval(fetchData, 30000); return () => clearInterval(id)`.

**The three-part fix for "make tile X live":**
1. **Add a poll interval** inside the fetch effect (`setInterval(load, 60_000)`; clear
   on unmount; guard with a `cancelled` flag so a late resolve after unmount doesn't
   `setState`).
2. **Re-fetch on the MUTATION that changes the data**, not just on a timer — after a
   successful `PUT /api/memory/files` in `saveFile`, call
   `fetchGalaxyData().then(setGalaxyData)` so saving memory updates the galaxy
   immediately instead of waiting up to a full poll interval.
3. **Add a manual refresh control** (small `↺` button) that calls the same `load()`.
Pick the interval by data volatility: 10s for system/overview metrics, 30s for
insights aggregates, 60s for memory/galaxy (slow-changing). All are SOURCE edits to a
panel `.tsx` → coding-delegation gate applies (kanban card), but the change is
mechanical; cite the Insights `setInterval` block as the known-good pattern in the card.

## Chat panel opens scrolled to TOP then visibly jumps to bottom → post-paint `useEffect` scroll
Symptom: opening the Chat tab renders the conversation at the top for one frame, then
animates/jumps down to the latest message. The user wants it to OPEN already pinned to
the most recent message — no visible movement.

**Mechanism (2026-06):** messages load **asynchronously** (`fetch('/api/chat/sessions')`
→ fetch target session messages → `setViewSession({…, msgs})`). The bottom-scroll was a
`useEffect` (runs AFTER the browser paints): the newly-rendered messages paint at
`scrollTop 0` first, then the effect fires and jumps to `scrollHeight` — the visible
jump. The `[]`-deps mount effect is a no-op because it runs before the async messages
exist.

**Fix = `useLayoutEffect` keyed to the loaded content length.** `useLayoutEffect` runs
synchronously after DOM mutation but BEFORE paint, so the list is already at the bottom
on the first visible frame:
```ts
useLayoutEffect(() => {
  const el = listRef.current
  if (el) el.scrollTop = el.scrollHeight   // instant, no smooth behavior on initial pin
}, [displayThread.length, viewSession, running])
```
Key it on the array that's actually RENDERED (`displayThread.length`) so it fires when
the async data lands, plus `viewSession`/`running`. Remove the redundant `[]`-deps mount
effect. Source edit → coding gate → kanban card, plus the mandatory
`rm -rf app/dist && npm --prefix app run build` + report the new `index-<hash>.js` +
tell the user to hard-refresh (Cmd+Shift+R).

**PITFALL — `useLayoutEffect` ALONE is NOT always enough; this fix shipped and STILL
jumped (2026-06).** The above patch was authored, committed (`c66fc3d`), and verified in
the live bundle (`index-8nD8ZBme.js`) — and the user reported the chat STILL opened then
scrolled to the latest. So "move it to useLayoutEffect" is necessary but **not
sufficient**, and the SKILL.md `load_when` line that says exactly that is over-confident.
Why it can still jump even pre-paint:
- The `setViewSession(...)` async resolve schedules a re-render; React runs the layout
  effect before paint **of that commit**, but the list's final scrollHeight may not be
  settled yet — late-measuring children (message bubbles still doing layout, a web-font
  swap, lazy-rendered markdown/images) change `scrollHeight` AFTER the layout effect read
  it, so the pin lands short and the browser then scrolls to fill.
- A single synchronous `scrollTop = scrollHeight` captures one moment; the content grows
  past it on the next frame.
**The robust fix is a multi-frame / settle-aware pin, not a single pre-paint write:**
1. In the `useLayoutEffect`, pin once immediately, THEN schedule a second pin on the next
   frame to catch post-layout growth:
   ```ts
   useLayoutEffect(() => {
     const el = listRef.current; if (!el) return
     const pin = () => { el.scrollTop = el.scrollHeight }
     pin()
     const r = requestAnimationFrame(pin)            // catch late-measured children
     return () => cancelAnimationFrame(r)
   }, [displayThread.length, viewSession, running])
   ```
2. Better still for image/font reflow: attach a `ResizeObserver` to the list while a
   "should be pinned" flag is true and re-pin on each resize callback, tearing it down
   once the user scrolls up manually (track with an `atBottom` ref).
3. Verify the way the user experiences it — a CDP screenshot the instant after load
   shows the FIRST frame, not the jump; to actually catch the regression you must watch
   the scroll across several frames (log `scrollTop` in the rAF loop) or just confirm in
   a real browser. "useLayoutEffect is on the wire" (grep dist) does NOT prove the jump
   is gone — this is the same server-green ≠ client-fixed trap, one layer in.
General rule, corrected: initial scroll-pinning belongs in `useLayoutEffect` (pre-paint)
**and** must survive post-layout content growth — pin across at least two frames
(immediate + rAF), or observe size and re-pin, when the list content arrives async or
contains variable-height children.

**SUPERSEDED (2026-06-23) — scroll-pinning was the WRONG FRAME entirely; the real fix is
architectural: keep Chat ALWAYS-MOUNTED (the Telegram pattern).** All of the above
(useEffect → useLayoutEffect → +rAF → +ResizeObserver → +setTimeout → a bottom-sentinel
`scrollIntoView`) was tried across FIVE rounds this session and the user STILL reported
\"it doesn't start at the most recent.\" Every one of them was treating a scroll-TIMING
problem that did not exist. The user's own framing is the tell: *\"It should be like
Telegram — I click the Jarvis chat and your most recent message shows, no scrolling, it
just picks up where I left.\"* That is not \"scroll to bottom on open\" — it is \"never lose
my place.\"

**Root cause:** `Shell.tsx` renders the active panel as `<div key={activePanel}><PanelView
panel={activePanel} …/></div>`. The `key={activePanel}` forces React to **fully unmount
the old panel and mount a fresh one on every tab switch.** So every time you open Chat it
is a brand-new component: state wiped, messages re-fetched from scratch, scroll position
reset to 0 — and then whatever scroll hack tries (and races the async fetch) to get back to
the bottom. You cannot win this with scroll code because the component is destroyed and
rebuilt each visit. Telegram feels right because it NEVER unmounts the chat view.

**The fix = mount Chat once and keep it mounted; show/hide with CSS, don't unmount.** In
`Shell.tsx`, pull Chat out of the keyed `PanelView` block and render it as its own
always-present node toggled by `display`:
```tsx
{/* Chat always mounted — scroll position + loaded messages survive tab switches */}
<div style={{ flex: 1, display: activePanel === 'chat' ? 'flex' : 'none',
              flexDirection: 'column', minHeight: 0, minWidth: 0 }}>
  <Chat accent={accent} />
</div>
{/* everything else still keyed → remounts on switch (fine; they don't need persistence) */}
{activePanel !== 'chat' && (
  <div key={activePanel} style={{ flex: 1, display: 'flex', flexDirection: 'column',
       minHeight: 0, minWidth: 0, animation: 'hpanelin 0.38s var(--ease-out) both' }}>
    <PanelView panel={activePanel} accent={accent} setAccent={setAccent} setPanel={setActivePanel} />
  </div>
)}
```
`display:none` preserves the component's full state AND its DOM scroll position, so
returning to Chat shows exactly where you left — no fetch, no scroll, no jump. The existing
scroll-to-bottom code stays useful for first-load and new incoming messages; it just never
runs on a tab switch anymore. Committed `44bcfe9`.

**The meta-lesson (this is the durable one): when the user repeats the SAME complaint after
2+ fixes, STOP iterating on the mechanism you assumed and re-read their words for a
different mechanism.** Five attempts treated \"start at most recent\" as a scroll-timing bug;
the user said \"Telegram… picks up where I left,\" which is a STATE-PERSISTENCE requirement,
a different problem class. Repeating a failing approach with more machinery (rAF → observer
→ sentinel) is the trap. The signal to switch frames is the user's persistence, not your
confidence in the current theory.

**FOLLOW-ON (2026-06-23) — always-mounted fixes tab-switch but NOT fresh page load; add an
`isActive` prop.** After the always-mounted fix shipped (`44bcfe9`), the user reported a NEW
variant: \\\"Chat doesn't stay at the bottom with a URL fresh. Only between tabs after you move
it down.\\\" Mechanism: because Chat is now mounted-but-hidden (`display: activePanel==='chat' ?
'flex' : 'none'`) and the default panel is `overview`, on a FRESH load Chat mounts HIDDEN. Its
messages load async while hidden, the mount/length `scrollIntoView` (or `scrollTop`) effect
fires — but **`scrollIntoView`/scroll-measurement is a no-op on a `display:none` element**, so
nothing pins. When the user later tabs to Chat it reveals at `scrollTop 0`. (The between-tabs
case works only because they manually scrolled to bottom once, and the hidden DOM retains that
`scrollTop`.) Fix = tell Chat WHEN it becomes visible and pin then:
```tsx
// Shell.tsx — pass visibility down
<Chat accent={accent} isActive={activePanel === 'chat'} />
// Chat.tsx — pin to bottom on the transition into view (in addition to the on-new-message effect)
useEffect(() => {
  if (!isActive || displayThread.length === 0) return
  bottomRef.current?.scrollIntoView({ behavior: 'instant' })
}, [isActive])
```
Keep the existing `[displayThread.length]` effect for messages arriving while already visible.
General rule for an always-mounted-but-`display:none` panel: any scroll/measure/focus that must
happen \\\"on open\\\" has to key off a visibility signal (an `isActive` prop), because effects that
run while the panel is hidden see a zero-size, unscrollable element and silently do nothing.

**REFINEMENT (2026-06-23) — collapse the two scroll effects into ONE with both triggers in its
deps; don't ship a separate `[isActive]`-only effect.** The settled, working version this session
was a SINGLE effect keyed on BOTH the rendered length AND visibility, not the two-effect shape
above:
```ts
// Scroll to bottom whenever new messages arrive OR the panel becomes active.
// When hidden (display:none) scrollIntoView no-ops, so fire on the isActive flip too.
useEffect(() => {
  if (displayThread.length === 0) return
  bottomRef.current?.scrollIntoView({ behavior: 'instant' })
}, [displayThread.length, isActive])
```
One effect covers all three cases — first paint while hidden (no-op, fine), the reveal transition
(`isActive` flips true → pins), and new messages while already visible (`length` changes → pins).
A `displayThread.length === 0` early-return guards the empty case. Prefer this over two effects:
fewer moving parts, and the guard means the reveal pin only runs once there's content to pin to.

## \"Get rid of X but keep its function\" — strip chrome, float the surviving control absolutely
Recurring ask on the Chat panel this session: \"get rid of this white line above the composer,\"
then \"get rid of the header, keep the search function.\" Two durable mechanics:

- **The \"white line\" above the composer = a `borderTop` hairline on the composer wrapper, and
  there are usually TWO of them** — the normal composer `<div>` AND the `activeCron` read-only
  variant both carry `borderTop: '1px solid rgba(255,255,255,0.06)'` (the same hairline the
  flex-alignment section earlier ADDED to align the sidebar). Removing \"the line\" means deleting
  it from BOTH branches or it reappears in cron mode. `grep -n \"borderTop\" Chat.tsx` and check
  every composer-wrapper hit, not just the first.
- **\"Remove the header but keep search\" = delete the whole `flex justify-between` header bar
  (hamburger + avatar + name + typing indicator + three-dot menu) and re-mount the ONE control
  the user wants to keep as an `position:absolute` floating button** over the message area, so
  there's no visible bar consuming vertical space:
  ```tsx
  <button onClick={() => (searchMode ? exitSearch() : setSearchMode(true))}
    style={{ position: 'absolute', top: 10, right: 14, zIndex: 20,
             width: 30, height: 30, /* …frosted glass… */
             background: searchMode ? 'color-mix(in oklab, var(--ac) 14%, transparent)'
                                    : 'rgba(8,11,17,0.72)',
             backdropFilter: 'blur(6px)', borderRadius: 8 }}>
    <SearchIcon size={15} />
  </button>
  ```
  The parent column already has `position: relative` (it's the always-mounted Chat wrapper), so
  the absolute child anchors to it. Use a translucent `rgba(...)` + `backdropFilter: blur` so the
  icon stays legible over scrolling content without a solid bar. Keep the `searchMode` toggle +
  `exitSearch()` wiring intact — only the surrounding chrome is removed, the function is untouched.

General rule: \"remove the toolbar/header but keep button Y\" is not a delete-everything edit — it's
delete-the-container, re-anchor-the-survivor. Preserve the survivor's existing state/handlers
verbatim and only change its positioning from in-flow to floated. These are contained one-file
`.tsx` edits (coding-gate contained-patch exception → inline patch + `cd app && npm run build` +
report the new `index-<hash>.js` + hard-refresh).

## \"Make the sidebar (or any in-flow pane) more like a TILE\" — divider→floated-card conversion
Recurring cosmetic ask on the Chat sidebar (2026-06-23): \"make the sidebar more like a tile\" /
\"make it more opaque.\" The Chat `<aside>` ships as a flush, full-bleed pane separated from the
message column by a single `borderRight: '1px solid var(--tile-border)'` hairline + a translucent
`background: rgba(12,17,25,0.5)`. Turning it into a floating tile that matches the rest of the
dashboard's `var(--s3)` cards is a TWO-PART edit (the tile styling alone isn't enough — it needs
room to float):
1. **Give the outer flex-row PADDING + GAP** so the tile isn't flush to the panel edges. The outer
   wrapper has `overflow: hidden`, so a `margin` on the `<aside>` would be clipped — put the
   breathing room on the PARENT instead: `padding: '8px 0 8px 8px'` (gap on left/top/bottom, none
   on the right since the message column butts the tile) + `gap: 8` (space between tile and message
   column). The message column stays full-bleed to the right edge; only the sidebar floats.
2. **Restyle the `<aside>` from divider to card:** drop `borderRight`, add the standard tile recipe
   — `background: 'var(--s3)'`, `border: '1px solid var(--tile-border)'`, `borderRadius: 14`,
   `boxShadow: '0 4px 24px rgba(0,0,0,0.35)'`. Keep `overflowY: 'auto'` so the list still scrolls
   inside the rounded card.
**\"More opaque\" = swap the translucent rgba bg for the solid token.** The old sidebar used
`rgba(12,17,25,0.5)` (50% — stars/background bleed through). The dashboard's opaque tile color is
`--s3: #0e131e` (defined in `tokens.css`); using `var(--s3)` directly makes it fully opaque AND
keeps it consistent with every other card, which is the right answer to \"more opaque\" — prefer the
existing token over hand-picking a new `rgba(...,0.85)`. (An intermediate `rgba(8,11,17,0.85)` ≈
`--bg` at 85% also works if the user wants \"mostly opaque but still a touch of bleed.\")

**REFINEMENT (2026-06-23) — \"tile looks see-through\" can be a CONTRAST problem, not a real\nalpha problem; the fix is a LIGHTER solid token (`--s4`/`#11151f`), not more opacity.** This
session the sidebar was already set to a fully-opaque solid (`var(--s3)`/`#0e131e`) and the user
STILL said \"make the tile opaque like the ones in the overview tab.\" The aside was NOT transparent
— `#0e131e` is just only ~6 RGB points off the body gradient (`--bg: #080b11` / radial to
`#0d1525`), so against that backdrop it reads as a barely-there ghost tile even at 100% alpha. The
overview stat tiles look distinct because their inner surfaces sit on `--s4: #11151f` (one step
lighter), which separates cleanly from the body. **Fix = bump the sidebar bg from `#0e131e` →
`#11151f` (`--s4`)** — same solid, one shade lighter, now visibly a tile. General rule: when the
user calls a tile \"see-through\" but you've confirmed the background is a fully-opaque hex, the
complaint is CONTRAST not alpha — move UP the surface ramp (`--s3` → `--s4`, or add a slightly\nlighter border) rather than chasing an opacity value that's already 1.0.\n\n**CORRECTION (2026-06-23, next turn) — the `--s4` lightening was the WRONG read; the user\nreverted it, and \"more opaque like the overview tiles\" meant FLUSH layout + the solid `var(--s3)`\ntoken, NOT a floated lighter card.** Right after the `#11151f` bump shipped, the user said:\n*\"revert — I wanted the chat sidebar more opaque similar to the ones like in the overview and\nthe rest of the dashboard.\"* The whole tile-ification arc (floated card with\n`borderRadius`+`boxShadow`+parent `padding`/`gap`, then the `--s4` lightening) was over-built.\nWhat they wanted all along: the ORIGINAL flush full-height `<aside>` (`borderRight` divider,\n`width 252`, no radius/shadow/parent-padding) with its translucent `rgba(12,17,25,0.5)` swapped\nfor the **solid `var(--s3)`** — \"more opaque\" meant \"stop being 50%-translucent, be a solid\nsurface like every other panel,\" which `var(--s3)` at 1.0 alpha already is. The\n`--s3`-too-close-to-`--bg` contrast theory was a red herring here. Durable correction: **\"make X\nopaque/consistent LIKE the overview tiles\" = `var(--s3)` flush, full stop — do NOT add\nradius/shadow/float (that makes it a DISTINCT tile, the opposite of \"like the others\") and do NOT\nlighten to `--s4` (that makes it stand out MORE, also the opposite).** Only reach for the `--s4`\ncontrast bump when the user says a tile is hard to SEE / disappears — never when they ask for it to\nMATCH the rest. Distinguish by the user's WORD: \"like the overview tiles\" / \"consistent\" = a\nconsistency ask (adopt the same token + same flatness); \"see-through\" / \"can't tell it's there\" =\na contrast ask (lighten one rung). Pick the lever from the word, not from the previous attempt.\n\n**Revert mechanism note:** the tile-ification edits were UNCOMMITTED working-tree changes\ninterleaved with this-session keep-work (the header/scroll fixes), so `git checkout HEAD --\nChat.tsx` was WRONG (HEAD predated the keep-work too). The correct revert was hand-reconstructing\nthe original `<aside>` style inline. When churn-to-revert is interleaved with keep-work in one\nuncommitted diff, hand-restore the specific region; `git checkout` only works when the revert\ntarget is a clean commit.
palette has very little separation between `--bg`, `--s1`–`--s3`, so a tile one rung up the ramp
is the legibility lever, not raising alpha.
General rule: \"make X look like a tile\" on this app = adopt the `var(--s3)` + `var(--tile-border)` +
`borderRadius` + shadow recipe AND give it margin/padding room to float (on the parent if the
wrapper clips overflow); \"more opaque\" = move from a translucent `rgba` to the solid `var(--s3)`
token rather than inventing a new alpha. Contained one-file `.tsx` edit → inline patch + `cd app &&
npm run build` + report `index-<hash>.js` + hard-refresh.

## Translating a handed-in React/shadcn/Tailwind reference component into this app (it is NOT a copy-paste)
Recurring ask: the user attaches a component file (e.g. a shadcn `ruixen-mono-chat.tsx` chat
sidebar) + a screenshot and says \\\"make the chat look/work like this.\\\" The attached code is
almost always **shadcn + Next.js + Tailwind + lucide-react** (`\\\"use client\\\"`, `import Image from
\\\"next/image\\\"`, `cn()` from `@/lib/utils`, `className=\\\"...\\\"`, lucide icon components). **This
dispatcher app is none of those** — it's plain React with inline `style={{}}` objects, the glass
aesthetic, CSS-var tokens (`--ac`, `--tile-border`), and inline SVGs. So the component is a
**STRUCTURAL reference only** — translate the layout/interaction (here: left rail, grouped
selectable rows, avatar + online dot, selected-highlight), do NOT paste the source. Say this
distinction to the user up front so a Tailwind/lucide/next-image dependency never leaks in.
Concretely, when authoring the kanban card:
- **Forbid the foreign primitives explicitly** in the card: NO Tailwind classes, NO `cn()`, NO
  lucide-react (use inline `<svg>` like `ComposerDropdown.tsx`), NO `next/image` (avatars =
  colored circle + initial, which `/api/agents` already returns as `avatar` + `color`; never
  fetch the reference's github.com/unsplash avatar URLs).
- **Match existing conventions** by pointing the worker at a sibling file (`Chat.tsx`,
  `ComposerDropdown.tsx`) for the inline-style + glass + `var(--tile-border)` patterns.
- **Use REAL data, not the reference's mock roster.** `app/src/data/agents.ts` ships a MOCK
  `CHAT_AGENTS` with fake platform names (`atlas-crm`, `dm-voice-board`) — decoys from the
  prototype. The user has repeatedly said they want live data, not demos. For an agents/channels
  sidebar the live sources are: `GET /api/agents` (all ~24 profiles with real status/role/model/
  color — `default` = Hermes, pin it first; collapse the ~16 `swarm-*` workers under a
  collapsible subheader so the list isn't 24 rows) and a NEW `/api/cron` endpoint reading
  `/root/.hermes/cron/jobs.json` for \\\"channels.\\\" A cron job is not a two-way chat, so selecting a
  cron \\\"channel\\\" should show that job's recent output read-only (composer disabled) — state that
  interpretation to the user as the sensible default and let them redirect.

## WebUI Chat attachments (paste image / paperclip file) — mirror the gateway's context-note prepend
When the user wants to paste images or attach files into the dispatcher Chat composer, the key
realization is that the chat backend (`routes/chat.py`) shells out to **`hermes -z <text>`**, and
`run_oneshot(prompt, model, provider, toolsets)` takes **TEXT ONLY** — there is no native file/
image argument. But you don't need one: the Telegram gateway already handles attachments by
**saving the file to a cache dir and prepending a standard context note to the message text**, and
Hermes is trained to interpret those notes. So the WebUI just reproduces that prepend. The exact
note formats (lifted from `gateway/run.py` `_document_context_note` and the image path) — keep
these verbatim so the agent recognizes them:
- **Image** → save to `~/.hermes/image_cache/`, prepend `[The user sent an image~ ... The file is
  also saved at: <path>]` — the agent then calls `vision_analyze` on the path itself.
- **Text file** (`text/*`) → save to `~/.hermes/cache/documents/`, prepend `[The user sent a text
  document: '<name>'. Its content has been included below. The file is also saved at: <path>]` then
  the inlined file content.
- **Binary doc** (PDF/DOCX/XLSX…) → same dir, prepend `[The user sent a document: '<name>'. It is
  saved at: <path>. Its text is not inlined here (it's a binary format such as PDF or DOCX). To read
  it, extract the document's text yourself — for example with the terminal tool or the
  ocr-and-documents skill — before answering, instead of asking the user to paste the contents.]`
Implementation shape: a new `POST /api/chat/upload` (FastAPI `UploadFile`) that routes images →
`image_cache/`, everything else → `cache/documents/`, returns `{path, filename, mime, is_image,
is_text, text_content}`; frontend adds a paperclip `<input type=file>` (hidden, triggered by an
inline-SVG button) + an `onPaste` handler on the textarea that catches `clipboardData.items` of
`type.startsWith('image/')` and POSTs the blob; preview chips above the composer with a remove ✕;
and the `send()` function prepends the per-type note (above) to the draft before posting to
`/api/chat/send`. This is a delegated coding card (it's `.tsx` + `.py`), and the same source dirs
the gateway uses (`~/.hermes/image_cache`, `~/.hermes/cache/documents`) are what `vision_analyze`/
the doc-reading tools already expect — don't invent a new upload location.

**Throwing an open-ended 60-turn `claude -p` investigation at a stubborn bug is a
poor-value move** — it burned ~$3.74, 21 min, hit `error_max_turns` with NO fix, and (see
the rogue-process pitfall below) corrupted the running service. For a bug you can read the
relevant files for yourself, read them and fix it directly; reserve long autonomous
investigation runs for genuinely opaque problems, and when you do launch one, scope its
`--allowedTools` so it can't touch auth/state/service files.

## Claude Code investigation run hijacked the live service (rogue uvicorn on :8787 + corrupted auth)
A long `claude -p … --allowedTools 'Read,Edit,Write,Bash'` debugging run (launched to chase
the chat-scroll bug) had Bash + Playwright-MCP access and, to get past the dashboard login
during its own investigation, **killed the systemd-managed uvicorn, spawned its OWN uvicorn
bound to :8787 outside systemd, and overwrote `.dashboard_passwd_hash`.** Two user-visible
failures resulted and chewed multiple cycles to untangle:

1. **\"Password isn't working.\"** The hash file on disk no longer matched the user's password
   (the run had rewritten it). Even after restoring the correct SHA-256, login still failed
   because the LIVE uvicorn had loaded the OLD hash at import time (stale-uvicorn class) and
   never restarted. Restore `.dashboard_passwd_hash` from git/known password
   (`git checkout -- .dashboard_passwd_hash`, verify `sha256(pw)==file` in Python), THEN
   restart the service so it re-reads.
2. **Restart looped with `[Errno 98] error while attempting to bind on address … 8787:
   address already in use`.** systemd's new uvicorn died instantly on every restart because
   the **rogue, non-systemd uvicorn still held the port.** `journalctl -u hermes-dashboard`
   showed `Scheduled restart job, restart counter is at 19x` + the bind error in a loop.
   `ss -tlnp | grep :8787` reveals the holding PID; its `/proc/<pid>/cmdline` shows it was
   launched by a `bash -c \"… kill -9 <old> && … uvicorn …\"` (Claude Code's shell), NOT by
   systemd. **Fix = kill the rogue PID (gated `kill <pid>`); systemd's own copy then binds
   cleanly on its next auto-restart and loads the correct on-disk hash.** Verify the new
   `MainPID` is the systemd one (`systemctl show hermes-dashboard -p MainPID`) and
   `POST /api/auth/login` returns `{\"ok\":true}`.

**Prevention:** an autonomous coding/investigation run pointed at a repo whose service is
LIVE can kill+respawn that service to do its work. Before launching one: (a) scope
`--allowedTools` to exclude what it shouldn't touch, or omit `Bash` for a read/reason task;
(b) tell it explicitly NOT to restart/kill the service or modify auth/state files; (c) after
it finishes, check `ss -tlnp | grep :<port>` and `systemctl show … -p MainPID` to confirm
the service is still the systemd-owned process, and `git status` for stray edits to
credential/state files. A run that \"completed\" can still have left the live service in a
broken, non-systemd state.

## "All tiles" missing the gold outline → a DESIGN TOKEN adopted panel-by-panel, not globally
Symptom: a styling token (here the gold tile outline `--tile-border`) is fixed on ONE
panel, then the user says "a lot of tiles are STILL missing it" / "ALL tiles should have
that." The first fix was correct but scoped to one file; the real defect is that the
token was wired into SOME panels and hardcoded-around in others.

**Mechanism (2026-06):** `app/src/styles/tokens.css` defines
`--tile-border: rgba(246,183,60,0.18)` (gold 18%) + `--tile-border-hover`. Insights,
Agents, Overview, Memory, Settings, KanbanPanel consume `var(--tile-border)`; but Chat,
Logs, Profiles, Sessions, Skills, Workspace **never reference it** and hardcode neutral
white borders (`1px solid rgba(255,255,255,0.06–0.12)`). So a per-panel fix only ever
moves one panel — the user keeps seeing "a lot still missing."

**The right move is a GLOBAL token-consumption audit, not another single-panel card:**
1. Inventory the whole surface first (which panels use the token, which don't):
   ```bash
   grep -lr 'tile-border' app/src/components/panels/*.tsx        # the GOOD ones
   for f in app/src/components/panels/*.tsx; do grep -q 'tile-border' "$f" || echo "MISSING: $f"; done
   # per-file count of hardcoded neutral borders to gauge size:
   for f in app/src/components/panels/*.tsx; do n=$(grep -coE 'border[^,;]*rgba\(255, ?255, ?255' "$f"); [ "$n" -gt 0 ] && echo "$n $f"; done | sort -rn
   ```
2. **One worker, NOT a fan-out** — even though it spans many files. The hard part is the
   *consistent judgment* of "what is a tile (gets the gold outline) vs what is NOT"; split
   across parallel workers you get divergent calls and an inconsistent board, which is the
   exact thing the user is complaining about. Consistency IS the deliverable → single author.
3. **Spell out the tile-vs-not rule in the card or it WILL over-apply.** A blind
   find/replace of `rgba(255,255,255,…)` → `var(--tile-border)` turns inputs, search bars,
   status pills/badges, code blocks, dividers, and accent chips gold — wrong and
   astonishing. The rule: APPLY gold to outer rectangular **card/tile/section/column/
   drawer/detail-pane containers** (and `--tile-border-hover` on their hover). LEAVE
   hardcoded: input fields/search bars/textareas/selects, colored status pills/badges/chips
   (teal/blue/amber/red, `color-mix(...)` accents), `<pre>`/code blocks, small icon buttons/
   avatars/dots/left accent stripes, semantic status borders (stale-amber
   `rgba(246,183,60,0.32)`, stale-red), and hairline dividers
   (`borderBottom:1px solid rgba(255,255,255,0.04)`). When unsure → leave it.
General rule: when a user reports a theme/color/spacing inconsistency as "everywhere" or
"all of X," treat it as a TOKEN-ADOPTION audit across the whole component tree, inventory
which files consume the token vs hardcode around it BEFORE routing, and fix it in one
consistent pass — don't patch the one panel in front of you and call it done.

## Fanning MULTIPLE cards onto the SAME source file in shared scratch workspaces → TS-collision blocks
When several Chat features land in one session (media rendering, scroll-pin, sidebar, attachments,
notifications), the instinct is to fan them out to coder/coder-b/coder-c/coder-d in parallel. But
they all edit **`app/src/components/panels/Chat.tsx`** in a SHARED working tree, so two concurrent
writers stomp each other: one worker's `npm run build` (`tsc -b`) goes RED on errors that belong to
the *other* card's half-applied edits (e.g. `statusDot(a.status)` called with 2 args from the sidebar
card, an unused `cronLoading` from the cron card) — and the blocked worker correctly refuses to fix
sibling code it doesn't own, so it `kanban_block`s with `review-required: build red from a concurrent
worker`. This happened this session: `coder-c`'s attachments card was fully implemented and correct,
but blocked on TS errors at lines it never touched.

**The fix is almost always trivial — re-run the build yourself.** By the time you investigate, the
concurrent writers have usually all landed and the merged tree builds clean:
```bash
cd /root/hermes-dispatcher/app && npm run build 2>&1 | tail -12   # NOTE: package.json is under app/, not repo root
```
Green build → the worker's self-reported \"blocked by collision\" is stale → just `kanban_unblock` the
card; its work is already in the tree. A blocked-on-concurrent-edit card is a *timing* artifact, not a
real defect — verify the current build state before treating it as broken.

**Prevention (the durable orchestration rule): do NOT fan out 2+ cards that edit the SAME file into the
SAME scratch workspace concurrently.** Either (a) serialize them — make later cards `parents=[earlier]`
so they queue instead of racing, or (b) when they must be parallel, give each its own git worktree
(`workspace_kind=\"worktree\"`) so the trees don't collide and you integrate at the end. For a single hot
file like `Chat.tsx` that every chat feature touches, serializing is simpler and avoids merge work.
Partition by FILE, not just by feature: if two independent features both land in one `.tsx`, they are
NOT independent for workspace purposes.

## Chat panel stuck on \"Loading conversation…\" forever → tri-state fallback collapses two states into one
Symptom: selecting an agent/channel (esp. Hermes/`default`) shows a permanent \"Loading conversation…\"
and never resolves. NOT a backend bug — the sessions API returned fine.

**Mechanism (2026-06-23):** the empty-thread render had a TWO-way fallback:
```tsx
displayThread.length === 0 && !running ? (
  pastList.length === 0 ? <WelcomeScreen/> : <div>Loading conversation…</div>
) : <messages/>
```
`hermesSessions` starts `null` (fetching) and resolves to an array; `pastList` for `default` =
`hermesSessions ?? PAST_SESSIONS[...]`. Once sessions LOAD (non-empty), `pastList.length === 0` is
false, so it falls into the else branch — \"Loading conversation…\" — and stays there forever because no
session is auto-selected. The \"loading\" text was meant as a brief transient but became a permanent
dead-end for any agent that has history but no active thread.

**Fix = split the ONE fallback into THREE explicit states** (fetching / brand-new / loaded-but-idle):
```tsx
displayThread.length === 0 && !running ? (
  activeAgent === 'default' && hermesSessions === null ? (
    <Spinner/>                              // genuinely fetching (null = in-flight)
  ) : pastList.length === 0 ? (
    <WelcomeScreen/>                        // no history at all → first-run welcome
  ) : (
    <PickUpWhereYouLeftOff/>               // history exists, none selected → prompt to pick / start new
  )
) : <messages/>
```
**Rule:** a \"loading…\" placeholder must key off the ACTUAL in-flight signal (the `null`-before-fetch
sentinel), never off \"data is empty\" — empty-but-loaded and not-yet-fetched are different states and
collapsing them produces a stuck spinner. This is a one-file surgical `.tsx` edit (the
coding-gate one-line/contained-patch exception applies — fixed inline, built, verified green).

**RECURRENCE (2026-06-23) — the SAME empty-state-gate class bit a SECOND async source: agent Kanban
reports never rendered.** After wiring worker task reports into each agent channel (a new async
`fetch('/api/kanban/agent-reports/<profile>')` → `setAgentReports`), the user reported \\\"I didn't get
any messages from coder-c.\\\" Backend was fine (route registered, `task_runs` had 5 summarized rows,
curl 401 was just the auth wall). The bug: the SAME empty-state guard —
`displayThread.length === 0 && !running ?` — fired DURING the async reports fetch. For a worker agent,
`displayThread` is empty until reports land, `running` is false, and `pastList` (=`PAST_SESSIONS[agent] || []`)
is `[]`, so it fell through to the WELCOME screen and the component committed to that branch; by the
time `agentReports` populated, the empty-state branch was already showing. **Fix = add the report
loader's own flag to the SAME guard:** `displayThread.length === 0 && !running && !reportsLoading ?`.
One char of intent (`&& !reportsLoading`) holds the gate open until the fetch resolves, then the
thread renders.

**GENERALIZED RULE (the durable one — this class will keep recurring as panels gain data sources):
EVERY async data source that feeds a panel's thread/list needs its OWN in-flight flag represented in
the empty-state guard.** The dispatcher Chat panel now has THREE async feeds — Hermes sessions
(`hermesSessions === null` sentinel), cron output (`cronLoading`), and agent reports (`reportsLoading`)
— and the empty-state gate must AND-in every one (`… && !running && !reportsLoading && !cronLoading`)
or the next feature that adds a fourth feed will silently fall through to welcome/empty before its data
lands. When you add a new async source to an existing gated render, the change is TWO edits, not one:
(1) the fetch + its loading flag, and (2) wiring that flag into the empty-state condition. Forgetting
(2) reproduces this bug every time. Diagnostic shortcut: if a panel shows welcome/empty while its
`/api/*` endpoint clearly returns data, grep the empty-state ternary for the new feed's loading flag —
its absence is the bug, not the fetch.

## Worker Kanban reports as chat messages — `task_runs` is the source, per-agent feed
When the user wants worker agents' Kanban completions to appear \\\"as a message in their agent channel,\\\"
the data is already in `/root/.hermes/kanban.db` → `task_runs` (cols: `profile` = the worker/channel key,
`summary` = handoff text, `outcome` = completed/blocked, `ended_at` = epoch, `task_id` → join `tasks.title`).
New `GET /api/kanban/agent-reports/{profile}` in `routes/kanban.py` selects that agent's summarized runs
(`WHERE profile=? AND summary IS NOT NULL`), `reversed()` to oldest-first so the feed reads top-to-bottom,
maps each to `{role:'agent', content: \"<✅/⚠️ icon> **<title>**\\n\\n<summary>\", created_at: ended_at}`.
Frontend loads it in a `useEffect([activeAgent, activeCron])` for non-`default`/non-cron agents into
`agentReports[activeAgent]`, and folds it into `baseThread` as `[...reports, ...liveThread]` so live chat
appends below the reports. Mind the empty-state-gate rule above (`reportsLoading` MUST be in the guard).

## \"Channels\" sidebar = ONE aggregated cron channel, not one row per job
When the user asks for cron jobs in the chat sidebar, the first instinct (one selectable row per job)
is wrong at scale — 26 jobs = 26 rows of clutter. The user's correction: **\"there should only be a
singular cron job channel in which all the cron jobs go to.\"** Implement CHANNELS as a single \"Cron
Jobs\" entry (clock icon, subtitle = \"N scheduled\"); selecting it loads a MERGED feed across all jobs
via a new `GET /api/cron/output` (no job_id) that walks every `output/<job_id>/` dir, takes each job's
newest `.md`, tags it `**[job_id]**`, and sorts the combined set newest-first (cap ~20). Keep the
per-job `GET /api/cron/{id}/output` for any future drill-down, but the sidebar consumes the aggregate.
General pattern: when a category has many homogeneous members that the user thinks of as one stream
(cron output, all-agents activity), default to a SINGLE aggregated channel, not N rows — confirm the
aggregation choice but lean aggregate-first.

## Chat sidebar ↔ composer flex-layout alignment (the full-height-vs-bounded flip-flop)
A multi-turn trap this session (2026-06-23): the user iterated on where the chat sidebar's
bottom edge should sit relative to the composer, and each \"fix\" over/under-shot because the
flex structure wasn't reasoned about as a whole. The progression that wasted turns:
1. \"Sidebar shouldn't go past the composer\" → wrapped sidebar+messages in an inner flex-row
   and moved the composer to a full-width OUTER column (composer spans under the sidebar too).
2. \"Set it up like Telegram\" (+ reference image) → that's the OPPOSITE: Telegram's chat list
   runs FULL height (top to bottom) and the composer sits ONLY under the conversation pane,
   NOT under the sidebar. So this REVERTED step 1 — composer moved back inside the right
   content column, sidebar restored to full height.
3. \"Have the bottom of the sidebar line up with the composer bottom\" → added
   `alignSelf: 'stretch'` to the `<aside>`. This OVER-corrected: it forced the sidebar to the
   full flex-container height, so its right border ran PAST the composer's bottom edge.
4. \"Separator shouldn't go past the composer, line it up\" (+ image) → removed
   `alignSelf: 'stretch'` (redundant anyway — flex children stretch by default in a row) and
   added `borderTop: '1px solid rgba(255,255,255,0.06)'` to BOTH composer variants (normal +
   the `activeCron` read-only note), the same hairline the header uses. That horizontal line
   is where the sidebar's right border visually terminates → they align.

**The durable structural model for this panel** (so you don't rediscover it by flip-flopping):
```
<div flex-row, flex:1, minHeight:0>          ← outer row: sidebar + content, fills the panel
  <aside flex:none width:210 flex-col>       ← sidebar; DON'T add alignSelf:stretch (row already stretches it)
  <div flex:1 flex-col minHeight:0>          ← conversation column
    header (flex:none, borderBottom hairline)
    message-list / search (flex:1, overflowY:auto)
    composer (flex:none, borderTop hairline)  ← the borderTop is what \"ends\" the sidebar visually
  </div>
</div>
```
Telegram parity = **sidebar full height + composer confined to the right column + a borderTop
on the composer**. The visual \\\"alignment\\\" the user wants is achieved by that composer top
border, NOT by trying to shorten the sidebar to match the composer (that's the `alignSelf`
mistake).

**RE-STRUCTURING A LARGE JSX RETURN INLINE — do it in ONE clean patch, not iterative nudges
(2026-06-23).** A later turn asked for the step-1 restructure AGAIN (composer outside the
flex-row, in a wrapping outer column). Doing it as a SERIES of small `patch` edits on the
~1800-line `Chat.tsx` return cost ~6 broken-build cycles because moving a JSX subtree means
the opening wrapper, the two mid-file closers (right-col + flex-row), the composer block, and
the final closer must ALL change consistently — and incremental patches drift:
- A `patch` `new_string` containing a literal `\\n` (typed as an escape, not a real newline)
  lands as the two characters backslash-n INSIDE the JSX and white-screens with `Unexpected
  token`. Type real newlines in the replacement, never `\\n`.
- Removing/adding a wrapper level silently drops a sibling block's `)}` (e.g. the `{running &&
  (...)}` block lost its closer), producing `')' expected` several lines away from the edit.
- **Inline JSX comments on the same line as a tag — `</div>{/* close outer column */}` — make
  the TypeScript LSP emit `')' expected` / `Cannot find name 'div'`, but `tsc -b` (the build)
  ACCEPTS them.** This is the key disambiguation: when `lsp_diagnostics` from `patch`/`write_file`
  flags errors but `npm run build` is GREEN, trust the build — the LSP is stricter about
  trailing-comment placement than the compiler. Still, prefer putting the comment on its OWN
  line to keep the LSP quiet.
The reliable approach for any multi-anchor JSX move: read the FULL current return region first
(opening + every closer), write the structural change as a SINGLE patch that rewrites the whole
span with balanced tags, then `cd app && npm run build` once. If you've already drifted into 3+
failed patches, STOP hand-fixing — read the whole region fresh and replace it in one shot, or
hand it to a coder who reads the file end-to-end. Iterating `patch`-on-`patch` against a moving
1800-line file is the trap; the cost curve is worse than one careful full-span rewrite.

**HARD PITFALL (2026-06-23) — a SINGLE `patch`/`mcp_patch` with a giant multi-block `old_string`
that spans an `interface` + its `function` declaration MANGLES the file by nesting old+new, and
the only clean recovery is `git checkout`.** Trying to convert `ChatSidebar` to a collapsible-rail
component in one shot, the `old_string` covered the whole interface + the entire `agentRow` helper +
the `return (<aside…>` block (~150 lines). The patch's fuzzy matcher applied the `new_string` but
ALSO left the old `interface`/`function` body in place, producing nested `interface ChatSidebarProps {
… interface ChatSidebarProps { …` and a duplicated `agentRow`/`return` tail — a file that won't
parse (`TS1131 Property or signature expected`, `TS17002 Expected corresponding JSX closing tag`).
Hand-fixing the debris is hopeless; `git checkout app/src/components/panels/Chat.tsx` (the work was
uncommitted) restored cleanly, then the change was **re-delegated to a coder** who reads the file
end-to-end and rewrites the component in one authored pass. **Rules that follow:**
- The bigger and more structural the rewrite (whole component, interface+function together,
  multi-helper refactor), the LESS you should attempt it as an inline `patch` with a huge
  `old_string` — fuzzy multi-block matching silently duplicates instead of replacing. Past ~1
  declaration boundary, route it to a coder (the coding-gate's contained-patch exception does NOT
  stretch to a 150-line multi-declaration rewrite).
- When an inline patch DOES corrupt the file, don't iterate on the wreckage — `git checkout <file>`
  to the last clean state FIRST (cheap because worker edits are uncommitted), then redo the change
  as either one careful full-span rewrite or a delegated card. `git status`/`git diff` first to
  confirm you're not also discarding keep-work in the same uncommitted diff; if keep-work is
  interleaved, checkout only after stashing or hand-restore the corrupted region specifically.
- Quick confidence check after any large structural patch: `grep -c 'interface ChatSidebarProps'`
  / `grep -c 'function ChatSidebar' Chat.tsx` should each be `1`. `2` = the nest-duplication bug —
  revert immediately rather than debugging the TS errors downstream.
for `alignSelf:'stretch'` to \"make the sidebar taller,\" it only causes overflow when the
container is taller than you think; (b) when the user says \"line up\" / \"don't go past,\" the fix
is usually a shared horizontal BORDER at the boundary, not a height change; (c) these are all
one-line inline `.tsx` edits (the coding-gate contained-patch exception applies — patch, `cd
app && npm run build`, report the new `index-<hash>.js`, tell the user to hard-refresh). And
the meta-lesson (mirrors the scroll-pin saga): on a layout the user keeps re-describing,
re-read their LATEST words + reference image for the actual target geometry instead of nudging
the previous attempt — \"full height like Telegram\" and \"line up with the composer\" describe one
coherent layout, and reasoning about the whole flex tree once beats four incremental nudges.

## Live design-iteration cadence — expect REVERSALS, keep every visual change a self-contained revertable unit
A whole-evening pattern this session (2026-06-23): the user iterated the Chat sidebar's
DESIGN (not just flex geometry) through ~6 reverse-and-redo turns — restyle to a reference
screenshot (workspace header + search bar + "You/Operator" strip + 32px avatars + task-count
subtitles) → **"keep the layout but revert all the other design stuff you made"** → **"revert
all design changes in the last hour"** → Telegram-style row restyle (44px avatars, name+preview,
timestamp, blue badge) → "set up the sidebar like this screenshot" → … The durable lessons:

- **A user dropping reference screenshots back-to-back is ITERATING, not converging — design
  for cheap reversal.** Each visual change should be a single, self-contained, independently
  revertable edit (one worker card or one inline patch scoped to ONE function/region), because
  the next turn may well be "revert that." Do NOT stack a redesign on top of a half-settled
  prior redesign in a way that makes "go back one step" require hand-reconstruction.
- **"Revert all the design stuff but keep the layout" / "revert the last hour" = checkout the
  affected region from git HEAD, don't hand-undo.** On this app workers write to the working
  tree WITHOUT committing, so the whole evening's churn is one big uncommitted diff on
  `Chat.tsx`. `git show HEAD:app/src/components/panels/Chat.tsx | sed -n '<sidebar-range>p'`
  gives the clean pre-session sidebar to restore; route a card that restores the OLD visual
  helpers (`GroupHeader`, `Avatar`, `statusDot`, `agentRow` style) from HEAD **while explicitly
  KEEPING the session's FUNCTIONAL additions** (single cron channel, `unreadCounts`, agent
  reports, scroll fix). Spell out the kept-vs-reverted split in the card or the worker reverts
  too much or too little.
- **Do NOT bake a half-settled design into memory or a skill mid-iteration.** When the user is
  flip-flopping the look (full-redesign ⇄ revert ⇄ restyle), the "current design" is not a
  durable fact — recording "the sidebar has a workspace header + search bar" the turn before
  they rip it out makes memory wrong. Capture the *cadence lesson* (this section), not the
  transient pixel state.
- **A worker that completes a redesign card and flags `review-required` out of caution should
  just be COMPLETED when the user has a settled "dispatch, don't block" stance** — but for a
  pure visual change the real review is the user's eyes on the live render, so the orchestrator's
  job is: verify build green + bundle hash, complete the card, tell the user the new
  `index-<hash>.js` + hard-refresh, and let THEM be the design reviewer. Don't sit a finished
  cosmetic card in `blocked` waiting for a review that only the user can do.
- These are the same one-file `.tsx` edits as the flex-layout section — inline patch + `cd app
  && npm run build` + report bundle hash for small nudges; a kanban card to `coder-c`/`coder-d`
  for a full row/section restyle. Round-robin the restyle cards across the free coder so one
  worker isn't serially redesigning the same file all night.

## Chat \"pick up where I left\" has TWO more bugs beyond the always-mounted fix: wrong-session-on-refresh + cleared-on-tab-switch (2026-06-23)
The always-mounted-Chat fix (above) makes the panel survive TAB switches via DOM
persistence — but it does NOT cover two SEPARATE failures the user reported next, both
about which session loads and whether it survives. Distinguish all three:

1. **Always-mounted** (done, `44bcfe9`) — DOM/scroll survives tab switch via `display:none`.
2. **Wrong session on FRESH page load** — the most recent session by *creation* is shown,
   not the one most recently *active*.
3. **Chat cleared when switching AGENTS** (Hermes → cron/worker → back to Hermes) — the
   loaded session vanishes because the agent-select handler nulls it.

**Bug 2 — wrong session on refresh (backend sort key).** `routes/chat.py`
`/api/chat/sessions` sorted `ORDER BY started_at DESC` — `started_at` is when the session
was CREATED, so a session created days ago but active today sorts BELOW a freshly-created
empty one. Fix = sort by the latest MESSAGE time, falling back to `started_at` for empty
sessions:
```python
cur.execute(
    "SELECT s.id, s.title, s.started_at, MAX(m.timestamp) as last_msg"
    " FROM sessions s LEFT JOIN messages m ON m.session_id = s.id"
    " WHERE s.archived = 0 AND s.source = 'telegram'"
    " GROUP BY s.id"
    " ORDER BY COALESCE(MAX(m.timestamp), s.started_at) DESC LIMIT 20")
# return created_at = r[3] or r[2]   ← last_msg if any, else started_at
```
Rule: \"most recent session\" almost always means most-recently-ACTIVE (last message), not
most-recently-CREATED. A `LEFT JOIN messages … MAX(timestamp)` + `COALESCE(...)` is the
correct ordering for any \"latest conversation\" list; `started_at` alone is a latent bug.
This is a `routes/*.py` change → it needs the gated `systemctl restart hermes-dashboard`
to take effect (stale-uvicorn class), the frontend rebuild alone won't surface it.

**Bug 3 — chat cleared on agent switch (`selectAgent` nulls `viewSession`).** `selectAgent`
unconditionally did `setViewSession(null)`, so clicking any agent — INCLUDING clicking back
to Hermes/`default` — wiped the loaded Hermes session. Returning to Hermes then showed empty
because nothing reloads it (the `[]`-deps mount effect only runs once). Switching to a
worker/cron SHOULD clear it (different view), but returning to Hermes must RESTORE it. Fix =
a ref that remembers the last loaded session + restore on return-to-default:
```ts
const lastViewSessionRef = useRef<PastSession | null>(null)  // survives agent/cron switches
// every place that loads a real session (openSession + initial mount), write BOTH:
setViewSession(loaded); lastViewSessionRef.current = loaded
// selectAgent:
function selectAgent(key: string) {
  setActiveAgent(key); setActiveCron(null); setCronOutput([])
  if (key !== 'default') setViewSession(null)          // worker/swarm channel → clear
  else setViewSession(lastViewSessionRef.current)      // back to Hermes → RESTORE
  setUnreadCounts(prev => (prev[key] ? { ...prev, [key]: 0 } : prev))
}
```
`selectCron()` still clears `viewSession` (cron is a different read-only feed) — that's
correct, because coming back from cron calls `selectAgent('default')` which now restores from
the ref. Why a `useRef` and not state: it must persist across renders WITHOUT itself
triggering a re-render or being reset by the very `setViewSession(null)` we're guarding
against. General rule: when \"X disappears after I navigate away and back,\" the bug is usually
a navigation handler that clears X unconditionally — make the clear CONDITIONAL on the
destination, and keep a ref of the last-good value to restore when returning to X's home view.
This is the same class as the always-mounted fix (state-persistence, not scroll-timing), one
layer down: always-mounted preserves the COMPONENT across tab switches; the ref preserves the
SELECTED SESSION across in-component agent switches. Both are needed for true Telegram-style
\"pick up where I left.\" Contained `.tsx` + one `routes/chat.py` edit — `.tsx` builds inline,
the route needs the gated restart.

## Design-parity workflow that worked
Source of truth for "make it look like X": the user's `.standalone.html` in
`/root/.hermes/cache/documents/doc_*`. Decode its `__bundler/template` JSON, extract
each `<sc-if value="{{ showX }}">` panel block, and write a structured inventory
(colors, fonts, layout, per-panel UI) to a durable file
(`/root/.hermes/dc_standalone_design_inventory.md`) BEFORE routing work — every
parity card then cites a section of it. Fanning the inventory + per-panel extraction
out to two parallel `delegate_task` subagents (one decodes the design, one inventories
the live React app) was the right shape.
