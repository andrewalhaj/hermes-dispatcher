# Porting upstream features INTO our layout (when adoption would replace the design)

Use this path when the user wants the official nesquena/hermes-webui feature set
but our design is a DIFFERENT LAYOUT ARCHITECTURE than upstream (full-screen
dashboard vs three-panel chat app — see the STOP-FIRST gate in
`adopt-official-upstream.md`). Here you keep OUR shell and bring the capabilities
in, rather than adopting upstream as the base.

## The decisive constraint (re-verify it yourself, don't trust assumptions)

The official `api/` package is **NOT importable** from the agent install. The
agent at `/usr/local/lib/hermes-agent` exposes `agent/`, `tools/`, `hermes_cli/`,
`gateway/` — there is no `api/` package, so `from api import streaming/workspace/
skills` fails structurally (ModuleNotFoundError). Confirm with:
```bash
python3 -c "import sys; sys.path.insert(0,'/usr/local/lib/hermes-agent'); import api" 2>&1
```
Consequence: you **port the CAPABILITY, not the upstream module code.** Adapt the
behavior into our `server.py` (FastAPI) + our `standalone.html` (DC bundle).

## Inventory before planning (fan out two read-only probes)

Two parallel `delegate_task` probes give the gap map fast:
1. **Upstream backend module inventory** — list `/root/projects/hermes-webui/api/
   *.py`, read each module's purpose + routes + agent imports, rate portability
   easy/medium/hard by `from api.*` coupling count. Output JSON.
2. **Our current state** — our `server.py` routes (`grep '@app\.'`), our existing
   standalone panels (decode the bundle), whether chat is real SSE, what's mock.
   Output JSON gap list.

Portability tiers that held this session:
- **easy** (zero/near-zero `api.*` coupling, copies cleanly): `galaxy_swarm.py`,
  `system_health.py`, `terminal.py`, `usage.py`, `sse_chunked.py`, journals.
- **medium** (bounded bridge, needs adaptation): `workspace.py`, `workspace_git.py`,
  `kanban_bridge.py`, `auth.py`, cron (YAML file I/O, no agent coupling).
- **hard** (owns global state or monkey-patches agent internals — DON'T port):
  `streaming.py`, `config.py`, `routes.py`, `models.py`, `profiles.py`,
  `session_lifecycle.py`. These are why "import upstream wholesale" fails.

## The phase plan that came out of this (priority order)

1. **Real streaming chat** — our chat is FAKE streaming: `subprocess hermes -Q →
   communicate()` blocks up to 120s, then re-chunks the finished text at 40chars/
   30ms. Fix = replace `communicate()` with an async `readline()` loop yielding
   each line as an SSE `delta` immediately; add `POST /api/chat/cancel` storing the
   subprocess PID per session. ~50 backend lines; the frontend SSE wiring already
   exists, it just gets faster. Biggest UX win, standalone change, no layout risk.
2. **Voice input** (~1h, pure frontend) — mic button + Web Speech API into the
   composer textarea.
3. **Mermaid rendering** (~1h, pure frontend) — detect ```mermaid fences, render
   via Mermaid.js CDN (SRI-pinned).
4. **Cron/Tasks panel** — read `~/.hermes/cron/*.yaml` + output logs; clean file
   I/O, no agent coupling. List/toggle/edit/run/history.
5. **Workspace file browser** — port `workspace.py`+`workspace_git.py` (FS logic
   standalone). Tree/preview/edit/git-badge. New panel in our layout.
6. **Skills CRUD** — extend our read-only `/api/skills` to full SKILL.md view +
   create/edit/delete.
7. **Session improvements** — CLI session bridge (Telegram sessions in sidebar
   with a badge), search, pin, archive, export.

Skip (too coupled): approval cards (`tools.approval` private symbols), passkeys,
full profile switching (monkey-patches agent paths), checkpoint/rollback.

## Deliverable when the user wants to hand this to a design agent

The output of "give Claude Design everything to edit in here" is a **handoff
package** under `~/.hermes/references/webui-design-handoff/` (use the
`agent-handoff-package` skill discipline — verify against live state, numbered
doc set, Golden Rules up front). The set that worked:
- `00-README.md` — system summary, Golden Rules (backup, `node --check` before
  restart, gate restarts, verify in browser not curl, no layout change without
  greenlight, don't invent data), read order.
- `01-architecture.md` — the DC bundle anatomy (the 4 `<script>` blocks: init,
  529KB manifest JSON of gzip+b64 assets, empty array, 221KB template JSON
  string), where CSS/JS live, the 3-layer edit model (template HTML → component-JS
  `_patch_standalone` patches → per-request `__RD_*` global injection), the
  `_replace_block` end-marker trap, the safe-edit-surface table.
- `02-design-system.md` — verified hex palette pulled from the live bundle (decode
  the manifest JS assets, `re.findall(r'#[0-9a-fA-F]{3,8}')`), the 3 fonts +
  weights, type scale, spacing grid, reusable component HTML templates (card,
  badge, nav item, section label), the `hpulse` keyframe, scrollbar CSS.
- `03-panels.md` — every panel: layout, elements, data source, what's wired vs mock.
- `04-feature-gaps.md` — the phase plan above with per-feature design specs.
- `05-editing-workflow.md` — backup → read → patch → `node --check` extracted
  component JS → gated restart → CDP screenshot verify; both template-HTML edits
  and JS-behavior patches; the JSON-escape and `</script>`-in-template traps.
- `06-quick-reference.md` — file paths, all routes, state.db + kanban.db schemas,
  health-check commands, Chromium CDP setup.
- `screenshots/` — one CDP screenshot per panel (auth via `/api/auth/login` →
  `hermes_session` cookie set in CDP `Network.setCookie`, navigate, capture).

Pull the palette + panel inventory from the LIVE bundle, not from memory — the
design system doc is only trustworthy if its hex values were extracted from the
served file this session.
