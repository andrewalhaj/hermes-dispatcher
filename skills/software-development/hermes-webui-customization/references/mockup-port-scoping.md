# Porting a design mockup to the WebUI: standalone bundles, skin ≠ panels

## A `.standalone.html` may be a SELF-EXTRACTING bundle — and it's instantly deployable (proven 2026-06-18)

Some `*.standalone.html` handoffs aren't plain HTML — they're a single-file
self-extracting bundle: a `<script type="__bundler/manifest">` (base64+gzip asset
map) + `<script type="__bundler/template">` + a `DOMContentLoaded` unpacker that
rebuilds blob URLs at runtime. Tells: a `#__bundler_thumbnail`/`#__bundler_loading`
splash, `<title>Bundled Page</title>`, and the two `__bundler/*` script tags. Inspect
without a browser:
```python
import re, json
html = open('<file>.standalone.html').read()
m = json.loads(re.search(r'<script type="__bundler/manifest">(.*?)</script>', html, re.S).group(1))
print(len(m), 'assets')  # fonts (woff2), the JS bundle, etc.
```
Key move: this bundle is the **fully-rendered preview of the React build the user
expects** — so when they say "it's supposed to look like THIS," you can drop the
standalone file straight in as the served `dist/index.html` for an INSTANT correct
render (back up the real index.html first; gate the write/restart). That buys a
visibly-correct UI in one step while you wire the real `src/` → backend in parallel.
It's a stopgap (mock data, no live API), not the finish line — follow with the real
wiring per `references/react-app-backend-wiring.md`.

## The skin-≠-panels trap, concretely

When the user hands a design mockup (a "Claude Design" handoff, a `.dc.html`
Disco-Component prototype, a `*.standalone.html` bundle) and says "make it look
exactly like this," the single biggest failure mode is **declaring victory after
porting the shell/skin while the redesigned PANELS were never built.** This
reference captures how to scope and verify a mockup port so "done" means what the
user means by done.

## The trap, concretely

This session shipped, verified, and reported "complete":
- a `mission-control` data-skin: `#080b11` background, `Space Grotesk`/`Inter`
  fonts, 227px text nav with WORKSPACE/SYSTEM groups, amber `#f6b73c` accent
  glow, animated starfield, recolored chat bubbles, accent-swatch picker, a
  redesigned login page.

Pixel checks PASSED (bg hex, sidebar width, accent-pixel counts, 55
mission-control CSS rules on the wire). The agent called it done.

The user's reaction: **"this whole thing doesn't look like that. I wanted it to
look exactly like that."** Because the mockup ALSO specified, as panel CONTENT
the live app never had:
- **Overview/Insights**: a "MISSION OVERVIEW" hero (greeting, date, status
  pills), four stat cards with glowing colored orbs, an agent-breakdown donut
  chart, a GitHub-style activity heatmap. The live Insights panel is a totally
  different "Usage Analytics" surface (CPU/RAM bars, LLM-wiki block, skill table).
- **Memory Galaxy**: a 3D canvas star-map view. The toggle was shipped but the
  user's real click-path (Memory tab → section submenu) renders an empty-state
  that never surfaces it.
- **Agents**: cards with circular progress rings, latency, success-rate.

A CSS-variable skin RECOLORS the panels that exist. It cannot create a donut, a
hero, or a heatmap the panel's `index.html`/`panels.js` never contained. Those
are separate build line-items, each needing markup + JS data-binding.

## The rule

**Decompose a mockup port into (1) shell/skin and (2) EACH redesigned panel as
its own deliverable with its own verify.** Never let "shell phases live" read as
"the redesign is done." A skin landing is necessary but not sufficient.

Scoping template for a mockup handoff:
- [ ] Shell: palette, fonts, nav layout, background, login (skin-overlay)
- [ ] Panel: Overview/Insights — hero + stat cards + donut + heatmap (markup+JS)
- [ ] Panel: Memory — galaxy canvas, REACHABLE via the real nav flow
- [ ] Panel: Agents — progress-ring cards
- [ ] Panel: Chat — bubble/context-bar deltas
Each line gets its own staging build + CDP screenshot + design-diff before it
counts.

## Verification: diff the mockup against the live app PANEL BY PANEL

Skin/pixel checks (bg hex, sidebar px, accent pixels) prove the SKIN landed —
they say nothing about whether a panel's markup matches the design. To verify a
mockup match you must compare renders side by side:

1. **Screenshot the design source** through the same CDP harness:
   ```bash
   mkdir -p /tmp/design-serve
   cp "<...>/Hermes WebUI Design/hermes-webui.standalone.html" /tmp/design-serve/index.html
   # background server:
   cd /tmp/design-serve && python3 -m http.server 8799 --bind 127.0.0.1
   ```
   Then CDP-navigate `http://127.0.0.1:8799/`, click through each panel
   (`document.querySelectorAll('[data-panel]')...click()`), `Page.captureScreenshot`.
   The `.standalone.html` is the FULLY-RENDERED mockup; the `.dc.html` is the DC
   prototype source (inline styles = the exact visual spec; `{{ }}`/`sc-for`/
   `sc-if` must be PORTED to the app's vanilla JS, never copy-pasted — no DC
   runtime ships).
2. **Screenshot each LIVE panel** (logged-in, skin forced) through CDP.
3. **Describe both with `vision_analyze` and compare** — list what the mockup has
   that the live panel lacks (hero? donut? heatmap? specific cards?). That delta
   IS your remaining build backlog. If `vision_analyze` is down
   (`No LLM provider configured for task=vision`), the skin can still be
   pixel-verified, but panel-CONTENT parity needs the visual compare — say so
   plainly rather than claiming a match you can't see.

## "Code served" ≠ "feature reachable"

A feature can be fully on the wire (`curl …panels.js | grep _fn` > 0, DOM node
present in a forced-state CDP check) and STILL be invisible to the user because
their actual navigation path never surfaces it (this session: the Memory Galaxy
toggle, hidden behind the section-submenu empty-state). Verify by driving the
REAL user flow — click the rail tab as a user would; do NOT shortcut with
`switchPanel('x')` + injected mock state, which can mount a node the normal flow
never reaches. Screenshot what the user would actually see.

## The mockup's MOCK DATA ships to live unless you rip it out and wire real APIs (proven 2026-06-18 follow-up)

When you transcribe a mockup's panel markup into the app, you also transcribe its
**fixture data** — and a design handoff is full of plausible-looking fake records
(this handoff: D&D-flavored agent names `rvc-runner`, `atlas-etl`, `npc-builder`,
`ops-bot` with hardcoded RUN/IDLE badges). If you port the panel and stop, those
fixtures become **live production data the moment you cut over.** They look real
enough that a skin/pixel check won't flag them — only reading the actual rendered
text reveals "wait, those agents don't exist." This is exactly the gap the user
means by "make sure everything is wired properly."

The rule: **every data array a ported panel renders is a wiring TODO, not done
work.** For each panel, after the markup is faithful, grep the new code for the
mockup's literal fixture strings and replace each array with a real fetch:
```bash
grep -rn 'rvc-runner\|atlas-etl\|npc-builder\|ops-bot\|<other mock names>' static/
```
Map each mock tier/record to a real source the backend already exposes:
- **Memory Galaxy** 6 tiers → `/api/memory` ({memory,user,soul,project_context})
  + `/api/sessions` (Conversations) + skills/knowledge count (Knowledge). SOUL.md
  and AGENTS.md are single blobs — split by markdown heading into multiple stars.
- **Overview donut "agent breakdown"** → `/api/insights` `models[]` (by session count).
- **Overview heatmap** → `/api/insights` `activity_by_hour[]`.
- **Overview stat cards / hero** → `/api/insights` totals.
- **Agents panel cards** → `/api/insights` `models[]` + `/api/gateway/status`;
  derive status with the SAME heuristic the panel already uses
  (`online` if top model & gateway running, `run` if sessions>5, else `idle`).
- **Rail AGENTS sidebar list** → SAME source/heuristic as the Agents panel so the
  two never disagree. Wrap the fetch in try/catch with a safe real fallback
  (just "Hermes LIVE") — NEVER fall back to the mock names.

Most of these endpoints exist already, so wiring is client-side and needs NO
backend restart. Picking real data over mock is also what makes the panel
trustworthy: a donut showing real `deepseek-v4-pro 66%` / `claude-sonnet-4-6 9%`
splits is the deliverable; a donut showing fictional agents is a bug.

## Post-cutover, verify the live DOM TEXT, not your own probe's selectors (proven 2026-06-18)

After cutover, "service restarted + console clean + panel visible" is NOT proof
the panels are right — a probe that counts `.donut circle` can return 0 because
YOUR selector guessed the wrong class name, not because the feature is missing.
The authoritative check is the rendered **text content** of the live panel:
```js
document.querySelector('#mainOverview').textContent.replace(/\s+/g,' ').trim()
// → "...110.0M tokens... AGENT BREAKDOWN 555sessions deepseek-v4-pro 366 66%..."
```
Real model names + real token totals in the text = real data wired. This also
catches formatter bugs cheaply: a token KPI reading "109740.6k" instead of
"110.0M" means `fmt()` doesn't handle millions/billions — add M/B (1e6/1e9) tiers.
When a structural probe returns suspicious zeros, dump the panel's actual class
histogram and `textContent` BEFORE concluding anything is broken; don't trust a
red number from a selector you wrote blind.

## Full-bleed panels: collapse the SECONDARY sidebar, reuse the existing `:has()` rule

A panel that should render edge-to-edge (Memory Galaxy, Overview, Agents) will be
boxed if the ~300px secondary `.sidebar` stays open — the canvas/grid starts at
`main.offsetLeft≈536` instead of spanning the viewport. The fix is one CSS line,
not JS: the app already collapses the sidebar for full-width panels via
`.layout:has(main.main.showing-overview) .sidebar, .layout:has(main.main.showing-agents) .sidebar{width:0;...}`.
Add the galaxy's active selector (`main.main.showing-memory.galaxy-on`) to that
same `:has()` group. No flicker, no JS toggle, consistent with the other panels.

## Don't over-report on skin-only pixel wins

The honest status after a skin port is "shell/skin is live and pixel-verified;
the redesigned panels (Overview hero, Memory Galaxy, Agents rings) are NOT built
yet." Leading with "Phase 3 complete — verified" when only the skin shipped is
the exact over-claim that burned this session. Report shell and panels
separately, and gate "looks like the design" on the panel-by-panel diff.
