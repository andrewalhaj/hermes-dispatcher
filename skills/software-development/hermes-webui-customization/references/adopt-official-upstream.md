# Adopting the official nesquena/hermes-webui upstream (keep our design + custom panels)

When the user says "implement github.com/nesquena/hermes-webui but with our
design / I want all its features" — the answer is **adopt the official repo as
the base, apply our design as the default skin, port our custom panels on top**.
NOT "re-implement 35+ official features inside our DC standalone." Proven
2026-06-19 (migrated the live WebUI from the custom DC standalone to upstream).

## ⛔ STOP-FIRST GATE: is "our design" a SKIN or a LAYOUT? (cost a deploy+revert 2026-06-19)

Before promising adoption-with-skin, answer ONE question: **is our design the
same three-panel chat-app LAYOUT as upstream (just recolored), or a different
layout ARCHITECTURE?**

- **Upstream layout** = three-panel CHAT APP: left session sidebar, center chat,
  right workspace; everything else is a panel inside that chat chrome.
- **This host's design (`hermes-webui-new` standalone)** = FULL-SCREEN DASHBOARD:
  each tab takes the entire viewport, Galaxy is a full-screen 3D canvas, there is
  NO persistent chat sidebar eating the main area. Default landing is an
  Overview/dashboard, not a chat thread.

These are **architecturally incompatible layouts**. A skin changes CSS variables
(colors, fonts); it CANNOT turn a chat-app shell into a full-screen dashboard.
Adopting upstream and calling our dashboard "the default skin" REPLACES the
user's design wholesale — this session it shipped upstream, the user said
"the entirety of the design is different, everything is gone… memory galaxy is
gone," and it had to be reverted.

**The rule:** if our design and upstream share the same layout architecture →
adoption-with-skin (this reference) is correct. If our design is a DIFFERENT
layout (full-screen dashboard vs chat app) → DO NOT adopt upstream as the base.
Instead **port upstream's capabilities INTO our layout** (new backend modules
wired into our `server.py` + new panels in our standalone), keeping our shell
intact. State the layout fork to the user BEFORE any service switch; don't say
"your design tokens ARE the default theme" until you've confirmed it's a recolor,
not a relayout. The "KEY DISCOVERY: our design IS already the upstream default"
section below is true ONLY for the color tokens — it is NOT true for the layout,
and the layout is what the user means by "our design."

## Why adopt, not port

- The official repo (`/root/projects/hermes-webui`, already cloned, git remote
  `nesquena/hermes-webui`) is production-grade, ~4500 commits, vanilla JS + Python,
  **no build step**. `static/*.js` edits are served directly on reload.
- It ships 35+ features our custom standalone never had: real SSE streaming chat,
  edit+regenerate, tool/thinking/delegation cards, session search/pin/archive/
  projects/tags, CLI session bridge, workspace file browser, voice input, Mermaid,
  approval cards, 15 skins, PWA+mobile, cron UI, skills browser, todos, spaces,
  slash commands, passkeys, session export/import, per-session token/cost.
- Re-porting all that into the DC runtime fights its limits (no innerHTML binding)
  and is never upstream-trackable. Adoption keeps `git pull` working forever.

## KEY DISCOVERY: our design IS already the upstream default

The custom standalone's design tokens are **already the upstream default dark
theme**. Confirmed by diffing:
- standalone `:root.dark`: `--bg:#0D0D1A; --accent:#FFD700; --sidebar:#141425`
- upstream `static/style.css` `:root.dark`: byte-identical values.

So "keep our design" = **zero skin work**. Just adopt; the dark theme matches.
(The three custom fonts — Space Grotesk, Inter, IBM Plex Mono — are a nice-to-have
HTML `<link>` add, not load-bearing; upstream uses a system-font stack via
`--font-ui` that looks the same in practice.)

## KEY DISCOVERY: upstream already has Kanban / Insights / Logs panels

`grep "nextPanel === '" static/panels.js` shows upstream already routes
`loadKanban() / loadInsights() / loadLogs()` and has `api/kanban_bridge.py`. So
the ONLY genuinely-custom panels to port are the ones upstream lacks — on this
host that was **Galaxy + Swarm** (the 3D memory galaxy + agent particle field).
Always grep the upstream panel dispatch FIRST so you don't re-port what's already
there.

## The adoption recipe (vanilla-JS upstream)

1. `git pull origin master` in `/root/projects/hermes-webui`. If the pull aborts
   because a local `static/index.html` stub blocks the merge, `git checkout
   static/index.html` FIRST (discard the stub), then re-pull.
2. **Add a custom panel — frontend** (`static/panels.js` + `static/index.html`):
   - `static/index.html`: copy an existing nav `<button>` shell into BOTH the
     `<nav class="rail">` (desktop) AND `<div class="sidebar-nav">` (mobile);
     set `data-panel="galaxy"`, tooltip, an inline SVG icon. Add a
     `<div class="panel-view" id="panelGalaxy">…<div id="galaxyContent">` block in
     `<main>` mirroring the existing `panelLogs` structure.
   - `static/panels.js`: add `if (nextPanel === 'galaxy') await loadGalaxy();` to
     the `switchPanel()` dispatch (~line 290), then append `loadGalaxy()` +
     renderer functions at end of file. Mirror upstream style: `$()`, `esc()`,
     `t()`, `api('/api/galaxy')`, `showToast()`.
   - Verify: `node --check static/panels.js` before any restart.
3. **Add a custom panel — backend**: new module `api/<panel>.py` with the builder
   functions (copy verbatim from the old `hermes-webui-new/server.py` builders),
   plus a small in-process TTL cache. Then in `api/routes.py` add `_handle_galaxy`
   / `_handle_swarm` handlers + dispatch cases in `handle_get`.
   - **AUTH PATTERN (critical):** upstream handlers do NOT call auth themselves.
     Auth is enforced CENTRALLY in `server.py`'s `do_GET` (`if not check_auth(...)
     : return`) BEFORE `handle_get` dispatches. So mirror `_handle_logs` exactly:
     `-> bool` signature, `return j(handler, data)` on success, `return
     bad(handler, ..., status=500)` on error. Do NOT invent a `_require_auth`
     call — there is no such helper. (`j`/`bad` come from `api.helpers`.)
   - `j()` returns `None`; `do_GET` treats `None` as "handled" and only 404s when
     a handler returns `False`. The `-> bool`/returns-`None` shape is the existing
     upstream pattern (Pyright warns; ignore — it matches `_handle_logs`).
4. **Service switch** (GATED — `/etc/*` + `systemctl restart`): the only fields
   that change in `/etc/systemd/system/hermes-webui.service` are
   `WorkingDirectory` and `EnvironmentFile` (both `…/hermes-webui-new` → `…/
   hermes-webui`). `ExecStart=…venv/bin/python server.py` is already correct —
   upstream `server.py` uses stdlib `ThreadingHTTPServer` with
   `if __name__=='__main__': main()`, NOT uvicorn. Back up the unit to
   `.bak-<ts>` first, `cp` the `.env` across, `daemon-reload`, `restart`, then
   verify `ActiveEnterTimestamp` MOVED (before/after) + auth login + `/api/galaxy`
   + `/api/swarm` return 200.

## PITFALL: porting big verbatim Canvas/renderer JS — do it INLINE, not delegated

The frontend port of the Galaxy renderer (3D perspective projection, marble
nodes, synapse-burst flicker, drag-orbit/scroll-zoom/click-inspect — ~300 lines
of verbatim-adapted Canvas-2D from `server.py`'s `_patch_standalone` js.replace
blocks) **timed out a delegated subagent at 900s**. Large faithful-port JS
authoring is sequential, source-tethered work: extract the original renderer
algorithm to `/tmp` (decode the standalone bundle's manifest assets / read the
`_patch_standalone` js.replace blocks), then author inline. Backend builder +
routes DID delegate fine (mechanical copy). Split the fan-out so renderer authoring
stays inline; only mechanical copy-and-register work goes to a subagent.

## Where the renderer source lives in the old standalone

The custom panels' real rendering code is in `hermes-webui-new/server.py`'s
`_patch_standalone()` as `js.replace(...)` / `_replace_block(...)` patches
(search `drawGalaxy`, `initGalaxyData`, `ensureSwarm`, `updateSwarmLegend`,
`__RD_GALAXY__`, `__RD_SWARM__`). The backend builders are `_galaxy_for_ui()` /
`_swarm_for_ui()` in the same file. Copy those verbatim; they already produce the
exact `{mem, tiers}` / `{profiles}` shapes the JS consumes.
