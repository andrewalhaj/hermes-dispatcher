# Kanban tab — structure map + legibility playbook

Concrete map of the Kanban tab in the vanilla-JS WebUI
(`/root/projects/hermes-webui/`, verified 2026-06). Re-grep before relying on
line numbers — they drift.

## Where things live

- **Markup**: `static/index.html`
  - Nav tab buttons: `data-panel="kanban"` (rail + top bar variants).
  - Filter sidebar: `.kanban-filter-stack` (search, assignee/tenant selects,
    include-archived / only-mine checks, bulk bar, new-task row).
  - Board area: `.kanban-board-wrap` > `.kanban-board#kanbanBoard`.
  - Board switcher + dispatcher buttons in the main-view header.
  - Modals: `#kanbanBoardModal`, `#kanbanTaskModal` (`.kanban-modal-overlay`).
- **Render logic**: `static/panels.js`, all `_kanban*` / `loadKanban*`:
  - `_kanbanCard(task, status)` — the card HTML. Topline = `kanban-card-id`
    + priority/tenant badges; then `.kanban-card-title`, `.kanban-card-body`
    (3-line clamp), `.kanban-card-meta` (assignee, 💬 comments, ↔ links, age),
    then `_kanbanCardQuickActions` (Complete/Archive buttons).
  - `_kanbanRenderColumn(col)` — `.kanban-column` with head label + count.
  - `_kanbanRenderSidebar(columns)` — the flat `.kanban-list` (status chip +
    title + meta).
  - `_kanbanCardStalenessClass(task)` — returns `kanban-card-stale-amber` /
    `kanban-card-stale-red` based on status+age thresholds.
  - `_kanbanRenderProfileLanes` — lane-by-profile alternate layout.
  - Drag/drop: `dragKanbanTask` / `allowKanbanDrop` / `dropKanbanTask`.
    NOTE: dropping into the `running` column is intentionally refused
    (claim path owns that transition; bridge rejects the PATCH 400).
- **Styles**: `static/style.css`, `.kanban-*` classes (~line 5400+).
- **Labels**: `static/i18n.js`, `kanban_*` keys (`kanban_status_ready`, …).

## Column statuses
`triage`, `todo`, `ready`, `running`, `blocked`, `done` (+ `archived`).

## Legibility-improvement playbook (the "make it intuitive" ask)

Root problems when a user says the board is "hard to digest":
1. All columns look identical — status invisible until you read the label.
2. Quick-action buttons render on EVERY card always (~30% of card is noise).
3. Staleness is a faint border tint — easy to miss.
4. Sidebar status labels are all the same muted gray — not scannable.
5. The card ID leads the topline instead of the title/what-matters.

CSS-only fixes (theme-safe via existing vars), in order of impact:
- **Status color-code columns**: colored top-border per status
  (triage=gray, todo=blue, ready=green, running=amber, blocked=red,
  done=faded green). Instant orientation.
- **Colored count badges** for running/blocked/ready columns.
- **Hover-reveal quick actions**: hide `.kanban-card-actions` by default,
  reveal on `.kanban-card:hover` — kills most card noise.
- **Stale stripe**: 3px left accent stripe on `.kanban-card-stale-amber/red`
  instead of a subtle border — overdue tasks pop.
- **Sidebar status chips**: color `.kanban-list-status` by status (needs a
  status class on the chip; ~1 line in `_kanbanRenderSidebar`).

Keep it to the visual layer — do NOT change card structure, column order, the
data model, or drag/drop logic. Present the plan, get greenlight, back up,
edit `style.css` (+ minimal `panels.js`), reload, eyeball live.

## Full restyle-from-a-reference-mockup (the "make it look like this file" ask)

When the user hands a target design (an HTML/`.dc.html` mockup, screenshot, or
Figma export) and says "make the Kanban tab look like this," it's the same
visual-layer discipline as above but card/column-wide. Proven recipe (done
2026-06, dark theme, reference was a `<x-dc>` component file):

1. **Read the mockup AND the live render functions side by side.** Map every
   mockup element to its live counterpart: `_kanbanCard()` (topline badges →
   title → meta row → quick actions), `_kanbanRenderColumn()` (head label +
   count), and the `.kanban-card*` / `.kanban-column*` CSS. Re-grep line numbers.
2. **Honor "keep the sidebar as-is" literally.** Touch only `_kanbanCard`,
   `_kanbanRenderColumn`, and appended CSS. Leave `.kanban-filter-stack`,
   `_kanbanRenderSidebar`, modals, and the detail view untouched unless asked.
3. **Per-element-color helpers go in `panels.js`, not inline magic numbers.**
   Add small pure functions near `_kanbanCardStalenessClass`:
   `_kanbanPriColor(p)` / `_kanbanPriBg(p)` (priority→color/translucent-bg),
   `_kanbanStatusColor(status)` (status→hex, the canonical palette below),
   `_kanbanInitials(name)` (assignee→2-char avatar text). Keeps the card
   template readable and the palette in one place.
4. **Drive the card's left accent stripe with a CSS var, not a class explosion.**
   Emit `style="--kpc:${priColor}"` on the `<article>`, then in CSS:
   `border-left:3px solid var(--kpc,var(--border))`. One var covers every
   priority without N status classes.
5. **Replace emoji metrics with inline SVGs** (💬→speech-bubble path, ↔→link
   path) for a crisp look that matches polished mockups.
6. **Avatar circle for assignee**: 20px round, `IBM Plex Mono`, dark text on a
   status-colored bg — `_kanbanInitials()` + `background:${statusCol}`. Replaces
   the plain `@name` text.
7. **Column head status dot**: prepend an 8px `.kanban-col-dot` colored by
   `_kanbanStatusColor(col.name)` inside a flex span before the label.
8. **Fonts**: if the mockup uses specific faces (Space Grotesk / IBM Plex
   Sans+Mono), inject ONE Google Fonts `<link>` block into `static/index.html`
   `<head>` (before `pwa-startup.js`), then reference them in the appended CSS.
   Note: a `grep "Space Grotesk"` on index.html returns 0 because the URL is
   `Space+Grotesk` (URL-encoded) — grep the encoded form to verify.
9. **Scope dark-theme overrides under `.dark`** (e.g. `.dark .kanban-card{...}`)
   so light skins are unaffected; append the block at the END of style.css.

Canonical status→color palette (matches column top-borders + dots + avatars):
`triage #8b85f0 · todo #5b9df5 · ready #f5b942 · running #2dd4bf ·
blocked #f56565 · done #48bb78 · archived #6a6a82`.

**Verification gates before declaring done** (server-side green ≠ client-side
rendered — the house rule):
- `node_modules/.bin/eslint --no-config-lookup -c eslint.runtime-guard.config.mjs "static/panels.js"` — empty output = clean. (The repo ships ESLint as a runtime
  guard; run `npm install --silent` first if `node_modules/` is absent — that's
  a missing-dep state, not a broken tool.)
- Prove all three assets are on the wire:
  `curl -s "http://127.0.0.1:8787/static/panels.js?v=x" | grep -c _kanbanPriColor`
  (and the same for a new CSS class + the font link). Non-zero = live.
- Then hand the user the hard-refresh steps (see `references/cache-staleness.md`
  — Windows keystrokes + the `is not defined` fallback) and ask them to eyeball
  the live board; the sandboxed browser tool often can't reach `127.0.0.1:8787`.
