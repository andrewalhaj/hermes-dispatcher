# Feature Gaps — Planned But Not Yet Built

*These are the Phase 1-7 items from the feature-port plan. Full plan at:*
`~/.hermes/references/webui-feature-port-plan.md`

---

## Phase 1 — Real Streaming Chat *(HIGHEST PRIORITY)*

**Problem:** Chat currently uses `subprocess hermes -Q → communicate() (blocks up to 120s) → read reply from state.db → drip at 40chars/30ms`. Not real streaming.

**Fix:**
- Replace `communicate()` with async `readline()` loop on stdout
- Each token line → `event: delta\ndata: {"text": line}` immediately
- Add `POST /api/chat/cancel` → kill subprocess
- Add Cancel button in composer
- Store subprocess PID per session in a dict

**Design work needed:**
- Cancel button in composer (small ✕ next to send, appears during active stream)
- "Thinking..." / typing indicator while first token hasn't arrived yet
- Tool call cards (if we add them): collapsible row showing tool name + args + result

**Backend file:** `/root/projects/hermes-webui-new/server.py` lines 3028-3136

---

## Phase 2 — Workspace File Browser

**New panel** in nav under WORKSPACE section.

**Layout design needed:**
- Left column: directory tree (expandable folders, file icons by type)
- Top: breadcrumb nav
- Right/main: file preview (text/code with syntax highlight, images inline, markdown rendered)
- Bottom bar: file actions (edit, create, delete, rename, download)
- Git badge in header: branch name + dirty count

**Backend routes to build:**
- `GET /api/files?path=<dir>` → listing
- `GET /api/files/read?path=<file>` → content
- `POST /api/files/write` → save
- `DELETE /api/files/delete`
- `POST /api/files/mkdir`
- `POST /api/files/rename`
- `GET /api/workspace/git` → branch + dirty

**Data source:** `~/workspace` (default workspace) and any path the agent is working in.

---

## Phase 3 — Cron / Tasks Management Panel

**New panel** — replaces or extends the current empty placeholder.

**Layout design needed:**
- List view: cron name, schedule string, enabled toggle (pill), last-run timestamp, manual run button
- Click row → detail/edit view:
  - Schedule input (e.g. "0 9 * * *")
  - Prompt textarea (the full prompt/instructions for the cron)
  - Enabled toggle
  - Delivery target (where the output goes)
- Run history pane: last N outputs with timestamps, collapsible
- "New cron" button → modal with same fields

**Data source:** `~/.hermes/cron/` YAML files + `~/.hermes/cron/output/` logs.

---

## Phase 4 — Skills CRUD

**Upgrade existing Skills panel** (currently read-only list).

**Changes needed:**
- Expandable cards: click skill → full SKILL.md rendered as markdown
- Edit button → textarea modal with raw SKILL.md + Save
- New skill button → blank modal with frontmatter template
- Delete with confirm dialog
- Category grouping with collapsible sections

---

## Phase 5 — Session Improvements

**Upgrades to Chat panel session list:**
- CLI badge (gold "cli" chip) for sessions that came from Telegram/terminal
- Search input at top of session list
- Per-session `⋯` context menu: pin, archive, export (Markdown), delete
- Pinned sessions float to top with a pin icon
- Date grouping: Today / Yesterday / Earlier

---

## Phase 6 — Voice Input *(~1 hour, no backend)*

**Add to Chat composer:**
- Mic button (left of send button)
- Web Speech API: `new SpeechRecognition(); continuous: false; interimResults: true`
- Interim results shown live in textarea
- Final result appended to existing textarea text
- Auto-hides if `!('SpeechRecognition' in window)`

---

## Phase 7 — Mermaid Diagram Rendering *(~1 hour, no backend)*

**In Chat message renderer:**
- Detect ` ```mermaid ` fences in assistant responses
- Call `mermaid.render()` on those blocks
- Load Mermaid.js from CDN with SRI hash in `<head>`
- Fallback to raw code block if Mermaid errors

---

## What's explicitly skipped (too complex)

- **Approval cards** — requires private symbols from `tools.approval` internals
- **Passkeys / WebAuthn** — low priority vs above
- **Full profile switching** — monkey-patches agent module-level paths, very fragile
- **PTY terminal** — could add later, `api/terminal.py` is portable, but not prioritized
- **Checkpoint/rollback** — requires agent's shadow-git checkpoint layout
