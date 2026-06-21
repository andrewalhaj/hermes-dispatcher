# Handoff: HERMES — Task Dispatcher

## Overview
HERMES is an agent-orchestration / task-dispatcher dashboard: a dark, "mission-control" web app where an operator watches a fleet of AI worker agents, chats with the orchestrator ("Hermes"), manages a Kanban task board, browses agent skills (plugins/tools), and inspects memory, sessions, logs, and settings. This handoff covers the full app, with extra detail on the three areas most recently built out: the **Chat planning timeline**, the **composer dropdown menus**, and the **Skills info drawer**.

## About the Design Files
The files in this bundle are **design references created in HTML** — a working prototype that demonstrates the intended look, layout, and interaction behavior. They are **not** production code to copy directly.

The prototype is authored as a "Design Component" (a single `.dc.html` file driven by a small runtime, `support.js`). That runtime is a prototyping convenience, **not** something to ship. Your task is to **recreate these designs in the target codebase's existing environment** (React, Vue, Svelte, SwiftUI, etc.) using its established component patterns, state management, and styling approach. If no codebase exists yet, pick the most appropriate framework (React + a CSS approach of your choice is a fine default) and implement there.

To preview the design: open `Hermes Task Dispatcher.dc.html` in a browser (it loads `support.js` and `hermes-board-v2-inline.js` from the same folder, plus Google Fonts and React from CDNs — needs network).

## Fidelity
**High-fidelity (hifi).** Final colors, typography, spacing, and interactions are specified. Recreate the UI pixel-accurately using your codebase's libraries and patterns. Exact hex values, sizes, and easing curves are given below.

---

## Design Tokens

### Colors
| Token | Value | Use |
|---|---|---|
| Background (app) | `#080b11` | Deepest app background / behind WebGL shader |
| Surface 1 | `#0b0f17` | Drawer / panel base |
| Surface 2 | `#0c1119` | Dropdown menu base |
| Surface 3 | `#0e131e` | Cards, stat tiles, meta cells |
| Surface 4 | `#11151f` | Agent (non-user) chat bubble |
| Surface 5 | `#070a0f` | Active-step code box |
| Accent (amber) | `#f6b73c` | Primary accent; brand, active states, links, user-bubble gradient base. Exposed as CSS var `--ac` and as the `accent` prop. |
| Accent gradient (user bubble) | `linear-gradient(135deg, color-mix(in oklab, #f6b73c 76%, #c2410c), #f6b73c)` | Outgoing chat bubble |
| Success green | `#4ade80` | Done states, "Enabled", success step rings |
| Error red | `#fb6f6f` | Error step, warnings |
| Info blue | `#8fb4ec` / `#8cb4ec` | Active-step lead text |
| Code purple | `#9b8cff` / `#9298ab` | Code lines, secondary mono text |
| Text primary | `#f4f6fb` / `#eef0f6` / `#f0f2f8` | Headings |
| Text body | `#b6bccc` / `#c6cad8` / `#d4d8e4` / `#d8dbe6` | Body copy |
| Text muted | `#9aa0b4` / `#9298ab` | Secondary |
| Text faint | `#6a7088` / `#565d72` / `#818799` | Labels, captions, timestamps |
| User-bubble text | `#1c1404` | Dark text on amber |
| Hairline border | `rgba(255,255,255,0.06)` – `0.12` | Card/panel borders |
| Hover surface | `rgba(255,255,255,0.05)` – `0.06` | Row/button hover |

### Typography
Three families (Google Fonts):
- **Space Grotesk** (500/600/700) — display & headings (panel titles, drawer title, plan titles, brand).
- **Inter** (400/500/600) — UI body text, labels, chat copy, buttons.
- **IBM Plex Mono** (400/500) — code, command signatures, key/values, durations, timestamps, numeric stats (`font-variant-numeric: tabular-nums` on numbers).

Representative scale (px): drawer title 25/600; panel header 20/600; plan title 14/600; body 13–14/400–500 line-height ~1.55–1.62; command sig 12; labels 9.5–10 uppercase `letter-spacing: 0.08–0.1em`; timestamps 9.5; mono detail 11 line-height 1.75.

### Spacing / Radius / Shadow
- Spacing rhythm: 4 / 6 / 8 / 11 / 14 / 16 / 18 / 20 / 22 / 26 px.
- Radius: pills/toggles `20px`+; cards `12px`; menus `11px`; detail boxes/cards `9–10px`; chat bubbles `16px` with a 5px "tail" corner; small chips `5–7px`; icon buttons `9px`.
- Shadows: cards on hover `0 14px 34px rgba(0,0,0,0.45)`; dropdown menu `0 16px 40px rgba(0,0,0,0.5)`; drawer `-22px 0 60px rgba(0,0,0,0.5)`; bubbles `0 2px 12px rgba(0,0,0,0.25)`.

### Motion (easing & durations)
- Standard easing: `cubic-bezier(0.16, 1, 0.3, 1)` (decelerate) for slides/expands.
- Dropdown menu open: `hmenuup` — `opacity 0→1`, `translateY(7px→0)`, `0.16s ease`.
- Dropdown label swap (on value change): `hdropswap` — `opacity 0→1`, `translateY(-5px→0)`, `0.24s cubic-bezier(0.16,1,0.3,1)`. Re-triggered imperatively by clearing+resetting `animation` (via a `setTimeout(0)` reflow nudge) so it replays even when the text node is reused.
- Plan collapse/expand: animate CSS Grid `grid-template-rows: 0fr→1fr` + `opacity`, `0.34–0.42s`.
- Spinner (active step / planning): `hspin` — `rotate(360deg)` `0.85s linear infinite`.
- Drawer in: `hdrawerin` — `opacity 0→1`, `translateX(34px→0)`, `0.3s cubic-bezier(0.16,1,0.3,1)`. Scrim: `hscrimin` opacity fade `0.2s`. Command rows stagger in: `hcmdrow` `translateY(8px→0)` `0.34s`.

---

## Global Layout

**Shell:** full-viewport, two-column. A fixed **left rail** (~`240px`) + a flexible **main content** column (`flex:1`, `min-width:0`, `min-height:0`, internally scrolling). A full-screen **WebGL "neuro" shader** sits behind everything and reacts to the pointer (decorative; reproduce with any subtle animated dark background or a static gradient if WebGL is out of scope).

**Left rail (top→bottom):**
1. Brand: "HERMES" wordmark (Space Grotesk) + a version badge.
2. `WORKSPACE` nav group: **Overview, Chat, Kanban, Agents**.
3. `SYSTEM` nav group: **Skills, Memory, Logs, Insights, Profiles, Settings** (names may vary slightly per section).
4. `AGENTS` live status list: each agent row shows a name and a status pill — `LIVE` / `RUN` / `IDLE`.

Nav items: icon + label, `12px` faint label for group headers (uppercase, `letter-spacing: 0.1em`). The **active** item has an amber left-edge accent bar (`position:absolute; left:-1px; top/bottom 25%; width:3px; border-radius:0 3px 3px 0; background: var(--ac); box-shadow` glow).

**Panel switching:** a single active-panel state (`state.panel` / `show<Panel>` flags) swaps the main column between Overview, Chat, Kanban, Agents, Sessions, Skills/Plugins, Memory, Logs, Settings.

---

## Screens / Views

### 1. Overview
- **Purpose:** at-a-glance mission control.
- **Layout:** header greeting; a row of status pills; a grid of stat tiles; an animated particle-swarm `<canvas>`.
- **Components:** stat tiles (`#0e131e`, radius 12) with a cursor-tracking glow; live system monitor sparklines (CPU/GPU/VRAM/net/mem) for two machines, updating on a RAF loop.

### 2. Chat  *(detailed)*
- **Purpose:** converse with the orchestrator (Hermes) and individual worker agents.
- **Layout:** header with agent switcher + session-history dropdown; scrolling message list (`flex:1; overflow-y:auto; padding:22px 26px; display:flex; flex-direction:column; gap:4px`); a composer footer. An animated starfield/shooting-star `<canvas>` sits behind the message list.
- **Agents:** Hermes + 4 workers. Switching agent swaps the thread.

**Message bubbles**
- Row: `display:flex; justify-content: flex-end` (user) or `flex-start` (agent); `margin:3px 0`.
- Bubble: `max-width:74%; padding:10px 15px; border-radius:16px` with a 5px tail corner (`border-bottom-right-radius:5px` for user, `border-bottom-left-radius:5px` for agent).
- User bubble: amber gradient (see tokens), text `#1c1404`, timestamp `rgba(28,20,4,0.6)`.
- Agent bubble: `#11151f`, `1px solid rgba(255,255,255,0.08)`, text `#d8dbe6`, timestamp `#565d72`.
- Bubble text 14px line-height 1.55; timestamp 9.5px right-aligned.

**Planning timeline (the key Chat feature)**
When the operator sends a message **to Hermes**, instead of a generic "typing…" indicator, an agent **plan block** is appended immediately and *is itself* the working indicator (no 3-dot bubble for Hermes). Other agents still use a 1.5s delay + canned text reply.

- **Card:** left-aligned, `width:100%; max-width:80%`, `background:#0e131e`, `1px solid rgba(255,255,255,0.08)`, `border-radius:14px`, shadow `0 2px 14px rgba(0,0,0,0.3)`.
- **Header (click to collapse the whole card):** left = status icon (20px) + title (Space Grotesk 14/600 `#eef0f6`); right = chevron that rotates `-90deg` when collapsed. Header bg `rgba(255,255,255,0.02)` + bottom hairline when open; transparent when collapsed.
  - Title & icon depend on state: **active** → spinning amber loader + "Hermes is planning the dispatch"; **all done** → green check + "Dispatch plan ready"; **idle/partial** → amber lightning bolt + "Dispatch plan".
  - Collapse animates `grid-template-rows: 1fr↔0fr` + opacity, `0.42s`.
- **Steps:** a vertical timeline. Each step = a 24px status node on a 2px connector line, a title row, and an optional expandable detail region.
  - **Node states:** success = green check on `rgba(74,222,128,0.16)`; active = spinning loader on `color-mix(in oklab, accent 22%, transparent)`; error = warning triangle on `rgba(251,111,111,0.16)`; pending = small dot on `rgba(255,255,255,0.06)`, whole row at `opacity:0.5`. Each node has a `box-shadow: 0 0 0 4px #0e131e` ring to mask the connector behind it.
  - **Title row:** clickable when the step has detail (cursor pointer, hover bg `rgba(255,255,255,0.03)`). Right side shows a mono duration (e.g. `0.4s`, `1.2s`, `…`) and a chevron (rotates `-90deg` collapsed). Active step title `#f0f2f8`/600; error `#fb6f6f`/600; else `#c6cad8`/500.
  - **Detail region:** animates `grid-template-rows: 0fr↔1fr` + opacity + margin-top, `0.34s`. Contains an optional **lead line** (mono 11px; spinner+blue text for active, or green check+text) and a **box** (`border-radius:9px; padding:11px 13px`, mono 11px line-height 1.75) holding either key/value rows (`grid-template-columns:84px 1fr`) or free text lines (with optional left indent). Box styling varies: neutral (`rgba(8,11,17,0.5)`), active-code (`#070a0f`), or error (`rgba(251,111,111,0.08)` bg, `rgba(251,111,111,0.22)` border).
- **Example 5-step plan (content to reproduce):**
  1. *Analyze dispatch request* — success, 0.4s. Lead: green check "Parsed operator intent — route to the worker pool". KV: Channel `dm-voice-board`, Target `rvc-runner`, Gate `latency < 220ms` (amber value).
  2. *Search skills & memory* — success, 1.2s. Lead: "vector_search · 3 matches retrieved". Lines: voice-rt / gpu-bench / obsidian matches.
  3. *Synthesize execution plan* — **active**, "…", expanded by default. Lead: blue spinner "Composing the dispatch sequence…". Code lines: `const plan = claim(readyTasks)` then 3 indented `→` steps, last one amber with a `▌` caret.
  4. *Check worker availability* — **error**, 0.8s. Error box: "Warning · capacity contention" + "No idle workers for 3 ready tasks; rvc-runner hit GPU OOM on model 3. Re-queuing behind the latency-gate run."
  5. *Dispatch to worker* — pending (no detail).
- **State:** `planMainOpen[msgId]` (default open) and `planStepOpen[msgId+'/'+stepId]` (default = step's `defaultExpanded`). Steps' statuses are static data in this prototype; in production they'd update as the agent progresses.

**Composer**
- Multi-line text input; left/right action clusters. Includes attachments, a bookmark and mic button, and a **slash-command palette** (typing `/` opens a command list). Send appends the user bubble (and, for Hermes, the plan block).
- Four **dropdown menu pills** (detailed next): Profile, Workspace folder, Model, Reasoning level.

### 3. Composer Dropdowns  *(detailed)*
Each pill is a trigger button + an absolutely-positioned menu that opens **upward** (`bottom:100%; margin-bottom:8px`).

- **Triggers:**
  - Profile: borderless, amber text+icon (person icon), `padding:5px 7px; border-radius:8px`, hover bg `rgba(255,255,255,0.05)`. Options: `default`, `reviewer`, `ops-bot`.
  - Workspace folder: pill `border:1px solid rgba(255,255,255,0.12); border-radius:20px; padding:5px 11px`, muted text, folder icon. Options: `Home`, `workspace`, `docs`, `archive`.
  - Model: same pill style, sun/gear icon. Options: `Claude Sonnet 4.6`, `Claude Haiku 4`, `Claude Opus 4`.
  - Reasoning: same pill style, dial icon. Options: `minimal`, `low`, `medium`, `high`, `xhigh`.
  - Each trigger label is wrapped in an `<span id>` so its swap animation can target just the label.
- **Menu:** `#0c1119`, `1px solid rgba(255,255,255,0.12)`, `border-radius:11px`, `padding:6px`, shadow `0 16px 40px rgba(0,0,0,0.5)`, open animation `hmenuup`. `min-width` 160–190px.
  - **Option row:** `display:flex; justify-content:space-between; padding:8px 10px; border-radius:8px; font-size:12.5px`. Selected row: brighter text `#e9ebf2`, bg `rgba(255,255,255,0.05)`, and a trailing amber check. Hover bg `rgba(255,255,255,0.06)`.
- **Behavior:**
  - Only one menu open at a time (`composerMenu` holds the open key or `null`). Clicking a trigger toggles its menu.
  - A full-screen transparent **click-away backdrop** (`position:fixed; inset:0; z-index:40`) closes any open menu. Trigger wrappers sit at `z-index:45` so they stay above it.
  - Selecting an option sets the field, closes the menu, and **replays the `hdropswap` label animation** — but only if the value actually changed.
  - **Implementation note that matters:** the label-swap is triggered imperatively (find the label by id, set `animation:'none'`, force reflow with `void el.offsetWidth`, set the animation). Do this on a `setTimeout(0)` (or `useLayoutEffect`/`requestAnimationFrame` in React) **after** the DOM updates so the keyframe replays on the reused node. In React, the idiomatic equivalent is keying the label span on the value (`<span key={value}>`) so it remounts and the CSS animation runs fresh — prefer that.

### 4. Kanban
- **Purpose:** task board for dispatched work, scoped by project.
- **Columns:** Triage → Todo → Ready → Running → Blocked → Done. Cards represent tasks. (In the prototype this is a nested child component, `hermes-board-v2-inline.js`; reimplement as a normal board component.)
- **Project dropdown IS the board title.** The board's heading reads `"<Project>  <visible>/<total>"` (e.g. "Board 18 / 18", "Atlas CRM 4 / 18"). The title text is a dropdown trigger: clicking it opens a chat-style animated menu (`hmenuup` open, `hdropswap` label-swap on change) listing each project with a color dot and its task count — `Board` (all), `DM Voice Board`, `Atlas CRM`, `Internal Ops`. Selecting filters the board's lanes to that tenant; the title updates to the project name + filtered/total count. A trailing chevron rotates 180° while open; a full-screen click-away backdrop closes it. State: the board owns `tenantFilter` (the dropdown sets it); tasks carry a `tenant` field; the filter is `tenantFilter === 'all' || t.tenant === tenantFilter`.
- **Toolbar (left→right):** the project-title dropdown · a **search field** (flexible, ~`flex: 1 1 340px`, min 240 / max 520px) with a search icon on the left **and a small `+` "new task" button docked inside its right edge** (26×26, absolute, `right:6px`) · a square **⚡ run-dispatcher** icon button (accent-filled, 34×34) immediately to the right of the search · a **Filters** button (tenant/assignee/archived/mine popover). The `+` creates a task in Triage titled from the search text (or "New task"); ⚡ runs the dispatcher.

### 5. Agents
- **Purpose:** fleet overview. 5 summary metric tiles + 5 agent cards (avatar, role, success ring, status, today/complete counts, model, last-active). Every tile and card is clickable — see **Universal Tile Info Panel**.

### 6. Skills (Plugins / Tools)  *(detailed)*
- **Purpose:** browse the tools the agent can call; click a skill to read full details; toggle to enable/disable.
- **Header:** title "Skills" (Space Grotesk 20/600) + subtitle "tools the agent can call — click a skill for details, toggle to enable" (12px `#6a7088`).
- **IMPORTANT:** the Skills panel container must be `position:relative` (the info drawer is `position:absolute` within it).

**Skill cards (grid)**
- Card: `#0e131e`, `1px solid` (selected → amber; enabled → `color-mix(in oklab, accent 28%, transparent)`; off → `rgba(255,255,255,0.06)`), `border-radius:12px; padding:16px; display:flex; flex-direction:column; gap:11px; cursor:pointer`. Hover: `translateY(-4px)`, brighter border, shadow `0 14px 34px rgba(0,0,0,0.45)`, transition `0.28s cubic-bezier(0.16,1,0.3,1)`.
- Card content: name + a status dot (green `#4ade80` when on, `#565d72` when off); category label; one-line description; a row of skill-command **chips** (mono 10px, `rgba(255,255,255,0.045)` bg, radius 5).
- A **toggle switch** on the card (38×22 track, 18px knob, knob x = 2px off / 18px on, track = accent when on). The toggle calls `stopPropagation()` so flipping it does **not** open the drawer.
- Clicking anywhere else on the card opens the **info drawer** for that skill.

**Skill info drawer (the key Skills feature)**
- Slides in from the right over a dimmed scrim.
- **Scrim:** `position:absolute; inset:0; z-index:30; background:rgba(4,6,10,0.5); backdrop-filter:blur(2px)`, fades in (`hscrimin` 0.2s). Click closes.
- **Drawer:** `position:absolute; top/right/bottom:0; z-index:31; width:452px; max-width:90%; background:#0b0f17; border-left:1px solid rgba(255,255,255,0.1); box-shadow:-22px 0 60px rgba(0,0,0,0.5)`, slide-in `hdrawerin` 0.3s. Internal `flex-direction:column`, body scrolls.
  - **Accent top strip:** `height:3px; background:accent; box-shadow:0 0 16px accent`.
  - **Header:** category chip (uppercase 9.5px on `rgba(255,255,255,0.05)`), name (Space Grotesk 25/600 `#f4f6fb`), status badge (dot + "Enabled"/"Disabled"; green on `rgba(74,222,128,0.12)` when on, faint on `rgba(255,255,255,0.05)` when off). A 32px **close (×) button** top-right (`rgba(255,255,255,0.05)` bg, radius 9, hover brightens).
  - **Description:** 13.5px line-height 1.62 `#b6bccc`.
  - **Meta grid:** 2×2, 1px-gap "table" look (cells `#0e131e`, outer `rgba(255,255,255,0.06)` border, radius 11). Cells: **Author**, **Version** (`v1.4.0`, mono), **Scope**, **Calls · 7d** (mono, `toLocaleString()`).
  - **Commands list:** section label "Commands" (uppercase 10px). Each command = card (`#0e131e`, radius 10, `padding:13px 14px`) with a mono signature in **accent** color (e.g. `read-note(path)`) and a 12.5px `#9aa0b4` description. Rows stagger in via `hcmdrow`.
  - **Enable/Disable button:** full-width, bottom. When **off**: amber bg, dark text, label "Enable skill". When **on**: `rgba(255,255,255,0.05)` bg + hairline border, light text, label "Disable skill". Contains a mirrored toggle switch. Flipping it updates the same `pluginOn[id]` state the card uses (drawer + card stay in sync).
- **State:** `skillSel` holds the open skill id (or `null`). Toggling enable/disable mutates `pluginOn[id]`.

**Skill data (reproduce verbatim):** 6 skills — Obsidian (Knowledge, core, v1.4.0, workspace vault, 71 calls; cmds read-note/search/create-note; ON), Notion (Knowledge, core, v0.9.2, team workspace, 38; pages/databases; ON), Dogfood QA (Testing, labs, v0.3.1, sandbox, 0; explore/report; OFF), Web Fetch (Web, core, v2.1.0, public web, 142; fetch; ON), GitHub (Dev, core, v1.7.3, 4 repos, 56; repos/prs/issues; ON), Voice RT (Audio, labs, v0.2.0, rvc-runner, 0; convert/bench; OFF). Full descriptions and per-command signatures + blurbs are in the source data array `PLUGINS` inside the HTML (see Files).

### 7. Sessions / Memory / Logs / Settings
- **Sessions:** list of past chat sessions with summary stats. Rows are clickable.
- **Memory — "Memory Galaxy":** a draggable **3D node field** on `<canvas>` — memories projected/rotated in 3D, colored/sized by tier (Notes, Project Context, Knowledge, Conversations). Interactions: **drag** to orbit, **scroll** to zoom, **hover** to highlight + show title, **click a node** to open its info card (bottom-right: tier, title, detail, importance/recall/age). Auto-orbit yaw advances slowly (`+0.0006`/frame — half the original speed) only when not dragging and not paused. **Spacebar toggles pause** (ignored while typing in an input); a clickable **Orbiting/Paused pill** sits top-left of the canvas (green dot = orbiting, accent dot = paused) and toggles the same `_gPaused` flag. State: `galaxyPaused`.
- **Logs:** a filterable log table (level/service/message/duration/status/tags).
- **Settings:** appearance (theme segmented control, accent swatches, language), agent defaults, behavior toggles, account/security, about. These sections hold live controls and are intentionally **not** click-to-info.

---

## Universal Tile Info Panel  *(detailed)*
Across the dashboard, **metric tiles, stat tiles, agent cards, and chart/content cards open a right-side info drawer on left-click.** One shared drawer renders all of them, driven by a single `tileInfo` state object (or `null`).

- **Drawer chrome:** identical to the Skills drawer but `position: fixed` (so it overlays from any panel). Dimmed scrim (`rgba(4,6,10,0.5)` + blur, `hscrimin` fade, click-to-close) + a `408px` (max `92vw`) panel sliding in from the right (`hdrawerin`). Accent top strip, category chip (uppercase), title (Space Grotesk 22/600), 32px close (×).
- **Body (all optional, driven by the info object):** a large accent-colored **value** (Space Grotesk 40/700), a **description** paragraph, a **stat table** (1px-gap rows, label left / mono value right), and an accent **action button** with a → arrow (e.g. "View the board", "Open chat with rvc-runner") that navigates and closes.
- **Info object shape** (built by a `mkInfo({...})` helper that fills defaults + `has*` booleans): `{ category, title, accent, value?, desc, stats: [{label,value}], actionLabel?, onAction? }`. `openInfo(o)` stores `mkInfo(o)`; `closeInfo()` clears it.
- **Content is tile-specific and pulled from the same data the tile displays — not placeholder text.** Examples:
  - **Overview stat tiles** (Tasks Run, Active Sessions, Tenants, Memory Items): value + a written blurb + a navigate action to the relevant panel.
  - **Agent Breakdown** card: lists every agent with its real task count and % share (the donut's data), sorted by load.
  - **Agent Activity Heatmap** card: lists each agent's busiest hour from the 24h grid.
  - **Agent Swarm** card: lists agents and their active counts.
  - **Agents panel:** 5 fleet-metric tiles (value + window) and 5 agent cards (status, success %, tasks today, completed/total, model, last active + "Open chat" action).
  - **Insights:** 4 KPI tiles, **Activity by Day** (window/busiest day/peak hour), **Token Breakdown** (in/out/total), **Models** (per-model share·tokens·cost), **Skill Usage** (per-skill calls·share).
  - **System Monitor** metric tiles (CPU/GPU/VRAM/Network): current value, machine, nominal/high-load state.
- **Already-interactive without this drawer:** Skills cards (their own detail drawer), Profiles cards, Sessions rows, and Memory nodes.
- **Per-tile wiring:** each tile/card carries an `onClick` that calls `openInfo({...})`. Handlers that need live data are defined where that data is built (the Overview `ov` builder, the Insights `ins` block) and referenced as `ov.onInfo*` / `ins.onInfo*`; simple ones live in the main view-model.
- **Logs:** a filterable log table.
- **Settings:** toggles + an accent-color swatch picker (the chosen color feeds `--ac` / the `accent` prop throughout).

---

## State Management
Single component state in the prototype; map to your store/hooks. Key state:
- `panel` / `show<Panel>` — which main view is active.
- `accent` — global accent color (default `#f6b73c`), threaded everywhere as `--ac` and the `accent` prop.
- **Chat:** `chatActive` (agent key), `chatThreads[agent]` (array of `{id, role, text, at}`; `role` ∈ `user|agent|plan`), `chatDraft`, `chatRunning`, `chatAgentMenu`, `chatPast` (history). Plan UI: `planMainOpen{}`, `planStepOpen{}`.
- **Composer:** `composerMenu` (open menu key or null), `cmpProfile`, `cmpFolder`, `cmpModel`, `cmpReason`.
- **Skills:** `pluginOn{id:bool}`, `skillSel` (open drawer id or null).
- **Tile info panel:** `tileInfo` (the `mkInfo` object currently shown, or null) — drives the universal right-side info drawer for every clickable tile/card.
- **Kanban board (child):** `tenantFilter` (active project; the title dropdown sets it), `projMenu` (title dropdown open).
- **Memory galaxy:** `galaxyPaused` (state mirror) + `_gPaused` / `_gYaw` (imperative canvas fields), `galaxySel` (selected node info card).
- Misc: live monitor sparkline buffers (RAF), toast, command palette open flag, etc.

**Behaviors to preserve:**
- Every metric/stat tile, agent card, and chart card opens the shared `tileInfo` drawer on click, with content pulled from that tile's own data.
- Board project switching is driven by the title dropdown (`tenantFilter`); the title reflects project + filtered/total count.
- Memory auto-orbit runs at half speed and only when not dragging and not paused; spacebar and the pill both toggle pause.
- Send-to-Hermes appends a `plan` message immediately (no typing indicator); send-to-worker shows running state then a canned reply after ~1.5s.
- Only one composer dropdown open at a time; click-away backdrop closes; label re-animates only on actual change.
- Card toggle uses `stopPropagation` so it doesn't open the drawer; drawer + card share `pluginOn` state.
- Collapse/expand (plan card, plan steps) via CSS-grid `0fr↔1fr` row animation.

## Assets
- **Fonts:** Space Grotesk, Inter, IBM Plex Mono (Google Fonts).
- **Icons:** inline SVG, stroke-based (Lucide-style, `stroke-width` ~2–2.6). No icon-font dependency; swap for your codebase's icon set.
- **No raster images.** Backgrounds are generated (WebGL shader, particle/starfield/galaxy canvases) — optional to reproduce; static fallbacks are acceptable.
- **React + a runtime** are loaded via CDN in the prototype; ignore for production.

## Files
- `Hermes Task Dispatcher.dc.html` — the full design. Markup lives in the `<x-dc>…</x-dc>` template; logic (data arrays incl. `PLUGINS`, `CHAT_AGENTS`, plan step builder `PLAN_STEPS()` / `buildPlan()`, and all handlers) lives in the `class Component extends DCLogic { … }` block near the bottom. **Read both** — exact copy, colors, and structure are there.
- `support.js` — the prototype runtime (do not ship; for previewing only).
- `hermes-board-v2-inline.js` — the nested Kanban board component used by the prototype (reference only).

To preview: open `Hermes Task Dispatcher.dc.html` in a browser with network access.
