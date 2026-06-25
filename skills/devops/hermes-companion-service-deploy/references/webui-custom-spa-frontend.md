# Replacing the WebUI frontend with a custom Vite/React SPA

When the user ships a redesigned frontend (Vite + React + TS + Tailwind, with
mocked data) and wants it wired to the real backend WITHOUT changing the visual
design, you are NOT deploying the upstream `nesquena/hermes-webui` HTML/JS — you
are building a separate SPA and dropping its `dist/` into the webui's `static/`
dir. The backend (`api/routes.py`, `api/streaming.py`, `api/kanban_bridge.py`)
stays the source of truth; only the frontend changes.

Verified end-to-end 2026-06-18 wiring a `hermes-react` redesign onto the live
`hermes.andrewskingdom.com` Cloudflare tunnel.

## Deploy shape

1. Build the SPA: `cd /root/projects/<spa> && npm install && npm run build` →
   produces `dist/index.html` + `dist/assets/*`.
2. Deploy: copy `dist/index.html` → `static/index.html`, then **`rm -rf
   static/assets` BEFORE copying `dist/assets/`** — do NOT `cp -r` over the
   existing dir. Vite emits content-hashed filenames (`index-<hash>.js`) that
   change every build; copying on top leaves the OLD chunks orphaned alongside
   the new ones, and a stale `index.html.bak` or cached client can reference a
   filename that no longer matches, giving a blank page that looks identical to
   the `base`-path bug. Always wipe-then-copy:
   `rm -rf static/assets && cp -r dist/assets static/assets`.
   **No service restart needed** — the webui serves static files off disk on
   every request; new files are live immediately. (Restart is only needed for
   Python backend changes.)
3. Verify the asset 200s at the SERVED path:
   `curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/static/assets/<hash>.js`

Keep backups before overwriting: `static/index.html.<variant>-bak` and
`static/assets.<variant>-bak/`.

## The two gotchas (each cost a debug round, both silent)

### 1. Vite `base` path → blank white page

**Symptom:** page loads completely blank/white, no visible error. The JS/CSS
`<script src="/assets/...">` tags 404 because the webui serves static under
`/static/`, not `/`. A 404 on the module script silently leaves `<div id="root">`
empty.

**Diagnosis:** `curl .../assets/<hash>.js` → 200 but `curl .../<hash>.js` (the
path the HTML actually references) → 302 (redirect to login) or 404.

**Fix:** in `vite.config.ts` set `base: '/static/'` so built asset references
become `/static/assets/...` matching where the backend serves them:
```ts
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: 'dist', assetsDir: 'assets' },
  base: '/static/',
});
```
Rebuild; confirm `dist/index.html` now has `src="/static/assets/..."`.

### 2. CSRF token → 403 on every POST (chat, kanban moves, skill toggles)

**Symptom:** GETs work (board, sessions render) but any mutation —
`POST /api/chat/stream`, `PATCH /api/kanban/tasks/{id}`,
`POST /api/skills/toggle` — returns `403 /api/chat/stream`. Chat shows
"Error: 403 /api/chat/stream".

**Why:** the backend's `_check_csrf` (in `api/routes.py`) requires the
`X-Hermes-CSRF-Token` header on mutating requests. The token is injected into the
served HTML at request time by `api/routes.py` (~line 7039, the
`/`/`/index.html`/`/session/*` branch) which `.replace()`s `__CSRF_TOKEN_JSON__`
and `__MAX_UPLOAD_BYTES__` placeholders — but ONLY when the request carries a
valid session cookie. A custom SPA's `index.html` that lacks the placeholder
script never receives the token.

**Fix (two parts):**

(a) The SPA's **source** `index.html` (the Vite entry, at project root — NOT
`dist/`) must carry the injection script in `<head>`, identical placeholder names
to the vanilla webui:
```html
<script>(function(){try{window.__HERMES_CONFIG__={maxUploadBytes:__MAX_UPLOAD_BYTES__,csrfToken:__CSRF_TOKEN_JSON__};}catch(e){window.__HERMES_CONFIG__={maxUploadBytes:0,csrfToken:''};}})()</script>
```
The `try/catch` is load-bearing: in Vite dev (`npm run dev`) the placeholders are
literal text and `JSON.parse`-style eval throws a `ReferenceError`, so the catch
falls back to empty — dev works through the same-origin proxy's Origin check
instead of a token. In production the backend substitutes real values before
serving.

(b) The API client reads the token and sends it on mutations:
```ts
function getCsrfToken(): string {
  return window.__HERMES_CONFIG__?.csrfToken ?? '';
}
// in the fetch wrapper, for non-GET/HEAD:
if (isMutating) {
  const t = getCsrfToken();
  if (t) headers['X-Hermes-CSRF-Token'] = t;
}
// always: credentials: 'include'
```

**Verify the injection is live** (mint a real cookie first). The password may
live in the systemd unit's `Environment=` lines OR in an `EnvironmentFile=`
(a clean rebuild commonly uses `EnvironmentFile=/root/projects/hermes-webui/.env`,
so grepping only the `.service` file finds nothing). Check both:
```bash
# password source A: inline in the unit
PASS=$(grep -h HERMES_WEBUI_PASSWORD /etc/systemd/system/hermes-webui.service \
       /root/projects/hermes-webui/.env 2>/dev/null | head -1 | sed 's/.*PASSWORD=//' | tr -d '"')
curl -s -c /tmp/tc.txt -X POST http://localhost:8787/api/auth/login \
  -H "Content-Type: application/json" -d "{\"password\":\"$PASS\"}"   # {"ok": true}
curl -s -b /tmp/tc.txt http://localhost:8787/ | grep __HERMES_CONFIG__
# want: csrfToken:"<64-hex>" substituted in, NOT the literal __CSRF_TOKEN_JSON__
```
The `.env` route is cleaner than inline `Environment=` — keep secrets out of the
unit file and point at it with `EnvironmentFile=`. Note the `.env` write itself is
write-gated (see the gate pitfall in SKILL.md) but a project `.env` under
`/root/projects/<proj>/` is a legitimate gated config write when inline won't do.
`GET /` unauthenticated returns the login page (302→/login), so always test
injection WITH the cookie, never bare.

## Wiring the panels (mock → real API)

Constraint the user states every time: **wire to the real backend WITHOUT
changing the visual design.** Touch `src/lib/store.tsx` + `src/lib/api.ts` and
the data hooks inside panels — never JSX structure, classNames, or CSS.

Real endpoint shapes (all same-origin, cookie auth):
- `GET /api/kanban/board?include_archived=false` → `{ tasks: [...], columns: [...] }`.
  Task fields: `id,title,priority,status,tenant,assignee,skills[],parents[],body,
  comments[],events[],runs[],links[]`. Map `body`→description, `branch_name`→branchName.
- `GET /api/sessions` → `{ sessions: [{id,title,created_at,updated_at,model,source}] }`.
- `GET /api/memory` → `{ memory, user, soul }` markdown strings (parse `§`
  separators into entries for a galaxy/list view).
- `GET /api/logs` → `{ logs: [{id,at,level,service,message,status,duration_ms,payload}] }`
  (map `duration_ms`→durationMs).
- `GET /api/skills` → `{ skills: [{name,description,category,enabled,pinned,runs}] }`;
  toggle via `POST /api/skills/toggle {name,enabled}`.
- `GET /api/insights?period=30`, `GET /api/settings`, `GET /api/models`,
  `GET /api/health/agent`.
- Chat: `POST /api/chat/stream {session_id?,text}` → `{stream_id,session_id}`,
  then `new EventSource('/api/chat/stream?stream_id=...')` consuming SSE events
  `delta` (`data.content`), `tool_start`, `tool_end`, `done`, `error`. Omit
  `session_id` to create a fresh session — the response returns the new id.

Always provide graceful fallback to the mock data if an endpoint errors or
returns empty — keeps panels from going blank on a partial backend.

## TypeScript build note (don't chase this)

`tsc -b` floods hundreds of `Cannot find name 'Set'/'Map'/'Iterable'` errors from
`node_modules/@types/*` (three.js, d3, react). These are PRE-EXISTING upstream
type issues; the project ships `"skipLibCheck": true` in tsconfig.json which makes
the actual `vite build` succeed regardless. Do not "fix" the lib target or rewrite
tsconfig — confirm `npm run build` exits 0 and produces `dist/`, and move on.
The patch-tool lint hook surfaces these on every `.ts` write; they are noise.

## Starfield / canvas background animation

The design's animated starfield is expected to BOTH twinkle (opacity sine wave)
AND drift (slow positional movement). A port that only twinkles looks static/wrong.
Give each star a `vx`/`vy` velocity (slow: ~0.003–0.018 px/frame at 60fps), advance
position each `requestAnimationFrame`, wrap around edges with a small margin, and
keep the opacity sine on top. `dpr`-aware canvas sizing + reseed on resize.
