# Live CDP Verification of the Auth-Gated WebUI

**Why this exists:** "Server up, HTTP 200, valid YAML, clean logs" does NOT prove the
WebUI app renders correctly in a browser. A WebUI redesign failed TWICE by shipping a
skin and declaring victory off server-side checks; the panels were broken/empty in the
actual DOM. The only ground truth for a frontend change is **driving a real headless
browser against the LIVE server, with real auth, then probing the DOM + console.**
Run this before claiming any WebUI visual/panel work is "done".

## Auth model (the part that trips you up)

The WebUI login is **form-based, password-only** (no username):
- `GET /` on an unauthenticated request → **302 → `/login?next=/`**. So plain
  `curl -u user:pass` (HTTP basic auth) gets bounced — wrong auth method. A 302 to
  `/login` with title `Hermes — Sign in` is the CORRECT unauthenticated response, not a bug.
- Login is `POST /api/auth/login` with JSON body `{"password": "..."}`.
- Success returns `Set-Cookie: hermes_session=<token>; HttpOnly; ...` (token ~129 chars).
- The password is `HERMES_WEBUI_PASSWORD`, readable from the running service's process env:
  ```bash
  tr '\0' '\n' < /proc/$(systemctl show hermes-webui -p MainPID --value)/environ \
    | grep '^HERMES_WEBUI_PASSWORD=' | cut -d= -f2-
  ```
- The auth route is CSRF-exempt (see `tests/test_issue1909_csrf_token.py`), so the bare
  JSON POST works without a token.

## Mint a session cookie

```bash
PW=$(tr '\0' '\n' < /proc/$(systemctl show hermes-webui -p MainPID --value)/environ \
      | grep '^HERMES_WEBUI_PASSWORD=' | cut -d= -f2-)
RESP=$(curl -s -i -X POST http://<host>:8787/api/auth/login \
        -H 'Content-Type: application/json' --data "{\"password\":\"$PW\"}")
COOKIE=$(echo "$RESP" | grep -i 'set-cookie' | grep -oE 'hermes_session=[^;]+' | head -1 | cut -d= -f2-)
echo "$COOKIE" > /tmp/live_sess.txt    # 200 OK + ~129-char token == good
```

## CDP harness

- Launch headless Chromium with a debugging port (long-lived, background):
  `chromium --headless=new --no-sandbox --disable-gpu --window-size=1440,900 \
   --remote-debugging-port=9222 --remote-allow-origins=* about:blank`
- Driver talks raw CDP over the websocket from `http://127.0.0.1:9222/json/list`.
  Requires the `websocket-client` python package. If `import websocket` fails in the
  default python, find one that has it (`/usr/local/lib/hermes-agent/venv` often does)
  or spin a throwaway: `uv venv /tmp/cdpenv && uv pip install --python /tmp/cdpenv/bin/python websocket-client`.
- **Inject the session cookie via CDP `Network.setCookie`** (name `hermes_session`,
  `domain` = the bare host/IP, `path` /, `httpOnly` true) BEFORE `Page.navigate`. Then
  navigate to `http://<host>:8787/` and the app loads authenticated.
- Drive the REAL nav flow (click the rail `.nav-tab[data-panel=...]`, then any toggle)
  rather than deep-linking — exercises the same code path the user hits.

## The two probes that actually catch bugs

1. **DOM ground-truth dump** — don't trust your own guessed selectors. Walk the panel's
   actual children and read `textContent` + a class histogram. Real rendered text
   (`"86 memories"`, `"110.0M tokens"`, real model names) proves real-data wiring; a
   guessed `.donut-seg` selector returning 0 is usually a WRONG SELECTOR, not a missing
   feature. Verify against the real class names before concluding anything is broken.
2. **Console capture** — collect `Runtime.consoleAPICalled` (error/warning) and
   `Runtime.exceptionThrown` while driving. "CLEAN — 0 errors" is a required gate; a
   server that's up can still throw on every render.

## Mock-vs-real wiring audit (the silent failure mode)

Ported design markup often hardcodes the design's **mock fixture data** (this session:
rail "AGENTS" list hardcoded `rvc-runner`/`atlas-etl`/`npc-builder`/`ops-bot` — D&D
fixtures wired to nothing). After a port, grep the live files for the mock fixture
strings AND probe the rendered DOM for them:
```js
!![].slice.call(document.querySelectorAll('.rail-agent-name'))
   .find(e => /rvc-runner|atlas-etl|npc-builder|ops-bot/i.test(e.textContent))
```
If true → it's still mock. Rewrite to fetch real data using the SAME endpoint + status
heuristic the full panel uses (e.g. `/api/insights?period=30` + `/api/gateway/status`,
status = online/run/idle by session count), wrapped in try/catch with a safe minimal
fallback (never fall back to mock names).

## Real-data sources for WebUI dashboards (confirmed shapes)

- `/api/memory` → `{memory, user, soul, project_context, ...}` — 4 memory tiers for free.
- `/api/sessions` → conversation history (Conversations tier / session counts).
- `/api/insights?period=30` → `{models:[{name,session_count,...}], activity_by_hour,
  totals}` — drives model-breakdown donut, 24h heatmap, agent cards.
- `/api/gateway/status` → live running flag for ONLINE badges.
- Memory Galaxy 6-tier mapping: Notes→MEMORY.md, User Profile→USER.md, Agent Soul→SOUL.md
  (split by markdown heading into multiple stars), Project Context→AGENTS.md (same split),
  Knowledge→skills/Supabase, Conversations→sessions.

## Visual fidelity without a vision model

When vision is rate-limited/unavailable, PIL pixel-sampling gives a deterministic,
provider-independent check:
- **Full-bleed check:** crop the secondary-sidebar zone (~56–356px x) and measure
  brightness; `<5%` bright == sidebar collapsed == panel is edge-to-edge.
- **Stars/clusters present:** crop the canvas region, count pixels with `max(rgb)>140`
  (bright stars) and colored pixels (`abs channel deltas >20`, tier glows).
- **Compare to the design reference image** by sampling the SAME metrics on both — if your
  render's star density is within range of the design PNG, "it's too sparse" from a vision
  model is idealized-galaxy bias, not a real gap vs THIS design.

## Full-bleed dashboard pattern (Overview / Agents / Galaxy)

The shell is rail + 300px secondary `.sidebar` + `<main>`. Panels trapped in the sidebar
render cramped. To make a panel full-width: render it as a `#main<X>` view inside
`<main>`, register it in `switchPanel`'s `showing-*` toggle list AND the chat-default
`:not(.showing-*)` chain, and collapse the secondary sidebar with a `:has()` rule:
`.layout:has(main.main.showing-<x>) .sidebar{width:0;...}`. For the galaxy (a sub-mode of
the memory panel) the selector is `main.main.showing-memory.galaxy-on`. Verify the canvas
`clientWidth` jumps (~903 boxed → ~1202 full-bleed) and sidebar `offsetWidth`→~1.
