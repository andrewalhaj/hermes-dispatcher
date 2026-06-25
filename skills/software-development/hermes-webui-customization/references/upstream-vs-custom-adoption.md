# "Implement the official Hermes WebUI's features into our site" — adopt-upstream vs. port-into-custom decision

When the user asks to bring the **official `nesquena/hermes-webui`** feature set
into our deployed UI ("implement its features with our design", "I want all its
capabilities"), this is an ARCHITECTURE decision FIRST, not an implementation
task. Do the inventory + present the fork BEFORE proposing any build. Proven
2026-06-19.

## Ground truth on this host (re-verify each session, but this is the baseline)

Two separate repos coexist under `/root/projects/`:

- **`/root/projects/hermes-webui`** — the official nesquena repo, already cloned,
  tracking `origin/master`. Vanilla JS + Python, NO build step, `static/*.js`
  served directly. ~40 `api/*.py` modules, 9.4k-line `panels.js`, 5.9k-line
  `style.css`, 15 built-in skins (`data-skin="ares|mono|poseidon|catppuccin|
  nous|zeus|…"`). This is the PRODUCTION-grade, upstream-trackable base.
  - NOTE: its `static/index.html` is a 19-line React/Vite shell
    (`<div id="root">` + `/static/assets/index-*.js`). The "vanilla JS, no build"
    description applies to the SERVED static dir's other assets; confirm whether
    the live build is the React bundle or the classic-`<script>` panels.js by
    reading what `server.py`/`api/routes.py` actually serves.
- **`/root/projects/hermes-webui-new`** — OUR custom DC-standalone (the thing the
  rest of this skill is about), currently the LIVE service on :8787
  (`hermes-webui.service` → `WorkingDirectory=/root/projects/hermes-webui-new`,
  `ExecStart=…venv/bin/python server.py`, serves `standalone.html` via
  `_patch_standalone`). Custom panels: Kanban, Memory Galaxy (3D), Agent Swarm,
  Insights. Simpler chat than upstream.

## The decision: adopt upstream as the base, add OUR panels on top

**Path A (recommended, almost always correct): adopt the official repo as the
foundation.** Switch the service to `/root/projects/hermes-webui`, apply our
visual design as a custom **skin** (CSS-variable palette/fonts/spacing — append-
only `data-skin`, reversible), and re-add our 4 custom panels (Kanban, Galaxy,
Swarm, Insights) as additional tabs wired to our existing backend routes. All
35+ upstream features (real SSE chat, tool/thinking/delegation cards, edit+
regenerate, cancel, session pin/archive/projects/tags, CLI session bridge,
workspace file browser, voice input, mermaid, approval cards, attachments,
context ring, Control Center, cron UI, skills browser, todos, spaces, slash
commands, passkeys, PWA/mobile) come for free, and `git pull` keeps us current
forever.

**Path B (almost always wrong): port upstream features into our DC standalone.**
Re-implementing 35+ features inside the DC bundle fights the runtime's limits
(no innerHTML/`sc-html` binding, JSON-template escape traps — see the other
references), is months of work, and is never upstream-trackable. Reject it
unless the user explicitly wants to keep the DC bundle as the base.

Rationale to give the user: the official repo is production-grade and actively
maintained (thousands of commits); our custom work is **4 panels**, not the
foundation. Make the custom panels additions to a maintained base, not a
hand-maintained fork of everything.

## The inventory technique (do this before proposing the fork)

1. Pull the upstream **README `## Features` section** verbatim — it's the
   authoritative capability list:
   `curl -sL https://raw.githubusercontent.com/nesquena/hermes-webui/master/README.md | grep -A 200 "^## Features"`.
   (`web_extract` LLM-summarizes and TIMES OUT on this 50–150KB README; the raw
   `curl … | grep` is faster and complete.)
2. Inventory OUR live UI's panels + routes:
   - panels: `grep -o 'show[A-Z][a-z]*' standalone.html | sort -u`
   - backend routes: `grep -E "^@app\.(get|post|patch|delete)" server.py`
3. Diff the two lists into "upstream has / we have / we both have". Present that
   table, then the Path A/B fork, then ask the ONE open question (what "our
   design" means: pull exact tokens from the live standalone, or a provided
   color/font spec).
4. The service switch + config edit are WRITE-GATE actions — present the diff,
   wait for greenlight, back up first. Don't switch the unit unprompted.

## Pitfall: don't start editing before the fork is decided

The reflex on "implement all its features" is to start wiring. STOP — the whole
deliverable hinges on Path A vs B. Porting into the DC standalone (Path B) is the
expensive default that looks like progress; adopting upstream (Path A) is the
right call but requires a greenlight on the service switch. Inventory → fork →
greenlight, in that order.
