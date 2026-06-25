# Design Audit: Standalone.html as spec vs React dashboard

When the user sends a `.standalone.html` and says "make our dashboard look like this" but
the live dashboard is a **React/Vite/TS app** (NOT the DC standalone), you're doing a
**design audit**, not a panel-port or data-wiring. The standalone is a visual reference;
the React app is the implementation target.

## Quick orientation

1. **Confirm which is live.** `systemctl status` + `ss -tlnp` to find the real served port
   and its `WorkingDirectory`. On this host (2026-06): the React app at
   `/root/hermes-dispatcher` served by `hermes-dashboard.service` on :8787 is the live
   dashboard — NOT `hermes-webui-new` or any standalone.html.
2. **Decode the standalone design.** Parse `__bundler/template` JSON → extract panel
   `<sc-if>` blocks, color tokens, layout patterns. The standalone's design tokens
   (colors, fonts) should already match — they were the source.
3. **Inventory the React app in parallel.** Use `delegate_task` to fan out: one subagent
   inventories the standalone design, another inventories the React source.
4. **Diff the inventories.** Compare per-panel: layout structure, specific UI elements,
   styling approach, what's wired vs mock.

## The parallel audit pattern

```python
delegate_task(tasks=[
  {"goal": "Extract design structure from standalone.html...",
   "context": "Parse __bundler/template JSON, extract each panel block..."},
  {"goal": "Inventory the live React dashboard at /root/hermes-dispatcher/app/src...",
   "context": "Check each panel component, styles, data wiring..."}
])
```

Both subagents need `terminal` + `file` toolsets. Results come back as structured
inventories you can diff manually.

## What to compare

| Layer | Design (standalone) | React (live) |
|-------|-------------------|--------------|
| Color tokens | hex values in template | `tokens.css` CSS vars |
| Fonts | `@font-face` blocks | Google Fonts link + CSS vars |
| Panels | `<sc-if value="{{ showX }}">` blocks | `components/panels/X.tsx` |
| UI elements | DC template markup | React TSX + inline styles |
| Glass effects | `backdrop-filter` occurrences | grep for `backdrop` |
| Animations | `@keyframes` names | `tokens.css` keyframes |
| Nav structure | `<button data-panel="...">` elements | `Shell.tsx` NAV_GROUPS |

## Common gaps to expect

1. **Canvas overlays missing** — DC standalone often has decorative canvases
   (`#hermes-neuro` with `mix-blend-mode: screen`) that React reimplementations skip.
2. **Glass morphism absent** — `backdrop-filter: blur(...)` doesn't survive porting
   unless explicitly implemented.
3. **Hover effects differ** — DC has specific `translateY(-4px)` + shadow values;
   React may have different transitions.
4. **Mouse-tracking glow** — DC implements per-element cursor-tracking radial glows
   that React components need to replicate from scratch.
5. **Chart layouts drift** — grid column ratios and chart types may not match.

## Output the gap analysis as a structured table

Present to the user: panel, specific gap, severity (High/Medium/Low), and proposed fix.
Then create kanban cards for the implementation work.
