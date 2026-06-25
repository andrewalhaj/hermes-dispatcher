# Hermes WebUI — Feature Port Plan
*Written 2026-06-19. Ground truth from live inventory.*

## Architecture Constraint (the one thing that drives everything)

Our WebUI (`hermes-webui-new`) is a **DC standalone bundle** served by a **FastAPI `server.py`**.  
The official Hermes WebUI is a **stdlib http.server monolith** with a 19k-line `routes.py`.  
**The official `api/` package is not importable from `/usr/local/lib/hermes-agent`** — that path has `agent/`, `tools/`, `hermes_cli/`, `gateway/`; no `api/` package. All `from api import streaming` paths fail structurally.

Consequence: we cannot drop-in the official modules. We port the *capability*, not the *code*.

---

## What We Keep (not touched)

- Full-screen dashboard layout (our panels take the whole viewport)
- Galaxy 3D canvas — full panel, 622 nodes
- Swarm particle field
- Kanban board (already fully wired, SSE live updates)
- Insights analytics
- Memory panel
- Dark gold design (standalone.html visual language)

---

## Current Gap Summary

| Gap | Current State |
|---|---|
| Chat streaming | Fake — `subprocess -Q → communicate() blocks 120s → re-chunk at 40 chars` |
| Workspace file browser | Missing entirely |
| Cron management panel | Missing entirely |
| Skills CRUD | Read-only list only |
| Session management | Basic list; no search/pin/archive/CLI bridge |
| Voice input | Missing |
| Mermaid rendering | Missing |
| Tool call cards | Missing |
| Cancel in-flight | Missing |
| Knowledge panel | Missing |

---

## Phase 1 — Real Streaming Chat (highest impact)

**What:** Replace fake streaming with real token-by-token output.

**Approach:** The agent CLI streams tokens to stdout as they arrive from the LLM when run interactively. Currently we batch with `communicate()`. Fix: replace with async `readline()` loop on stdout, yield each line as an SSE `delta` event as it arrives.

**Backend changes (server.py):**
- Replace `await asyncio.wait_for(proc.communicate(), timeout=120)` in `/api/chat/send`
- New loop: read stdout line by line, yield `event: delta\ndata: {"text": line}` immediately
- Store `proc.pid` in a session-keyed dict so cancel can `proc.kill()`
- Add `POST /api/chat/cancel` → kill the subprocess, yield `event: cancel`
- Add `GET /api/chat/stream/{session_id}` → SSE endpoint for persistent reconnect

**Frontend changes (DC standalone patch):**
- `sendChat()` currently polls `/api/chat/send` and waits for `done` event
- Wire `EventSource` reconnect on the existing SSE events — this already works, just needs the backend to stream faster
- Add Cancel button in the chat composer (calls `/api/chat/cancel`)
- Add tool-call card rendering: parse `event: tool_start` / `event: tool_end` events if the agent emits them

**Effort:** Medium. The subprocess loop change is ~30 lines. The cancel endpoint is ~15 lines. Frontend delta rendering is already there (SSE is wired), it just gets faster.

**Verification:** Type a long prompt, tokens appear word by word. Cancel button stops it.

---

## Phase 2 — Workspace File Browser

**What:** New full-screen panel showing the active workspace directory tree, with preview and inline edit.

**Approach:** Port `workspace.py` + `workspace_git.py` from the official repo. These have portability: medium (7 `from api.*` imports → need to adapt to our FastAPI, the FS logic is standalone).

**Backend changes (server.py):**
- Copy `workspace.py` and `workspace_git.py` into `hermes-webui-new/api/`
- Add routes:
  - `GET /api/files?path=<dir>` → directory listing (name, type, size, modified)
  - `GET /api/files/read?path=<file>` → file content (text) or binary download
  - `POST /api/files/write` → write file content
  - `DELETE /api/files/delete?path=<file>`
  - `POST /api/files/mkdir`
  - `POST /api/files/rename`
  - `GET /api/workspace/git` → branch + dirty count

**Frontend changes (DC standalone patch):**
- New panel: `showWorkspace` in the nav rail + sidebar-nav
- Panel content: directory tree (expandable), breadcrumb, file preview pane
- Match existing panel visual language (dark bg, var(--border), etc.)
- File type icons from existing icon set

**Effort:** Medium-high. The backend port is straightforward. The frontend tree UI is non-trivial in DC template syntax (recursive sc-for).

**Verification:** Click Workspace tab → see `~/hermes/workspace` tree → click a file → see preview.

---

## Phase 3 — Cron Management Panel

**What:** New panel to create, view, edit, pause, resume, delete cron jobs and see run history.

**Approach:** Cron jobs live in `~/.hermes/cron/` as YAML files (name, schedule, prompt, enabled). The official `api/routes.py` has `/api/crons/*` endpoints. We write our own clean implementation reading those YAML files directly — no agent coupling needed.

**Backend changes (server.py):**
- New module `api/crons.py`:
  - `GET /api/crons` → list all cron files + parse schedule/enabled/last-run
  - `POST /api/crons` → create new cron YAML
  - `PATCH /api/crons/{name}` → edit (schedule, prompt, enabled toggle)
  - `DELETE /api/crons/{name}` → delete
  - `POST /api/crons/{name}/run` → trigger immediately via `hermes cron run <name>`
  - `GET /api/crons/{name}/history` → read cron output logs from `~/.hermes/cron/output/`

**Frontend changes (DC standalone patch):**
- New panel: `showCrons` (rename from `showTasks` or add alongside)
- List view: cron name, schedule, enabled toggle, last-run timestamp, run button
- Edit modal: prompt textarea, schedule input, enabled toggle
- History pane: last N run outputs with timestamps

**Effort:** Medium. Cron YAML format is simple. The UI is a list + modal pattern that mirrors the Kanban task modal already in the bundle.

**Verification:** Click Tasks tab → see all cron jobs → toggle one off → run one manually → see output.

---

## Phase 4 — Skills Browser with CRUD

**What:** Upgrade the read-only skills list to a full browser: search, view full content, create, edit, delete.

**Backend changes (server.py):**
- Existing `GET /api/skills` returns name+description list — extend to include content
- `GET /api/skills/{name}` → full SKILL.md content + linked files list
- `POST /api/skills` → create new skill (write SKILL.md)
- `PATCH /api/skills/{name}` → update SKILL.md content
- `DELETE /api/skills/{name}` → delete skill directory

**Frontend changes (DC standalone patch):**
- Skills panel: searchable list with category grouping (already partially there)
- Click a skill → expand to show full markdown content
- Edit button → textarea modal with SKILL.md content, Save applies PATCH
- New Skill button → blank modal with frontmatter template
- Delete with confirmation

**Effort:** Low-medium. Backend is simple file I/O. Frontend is a search + expand pattern.

---

## Phase 5 — Session Improvements

**What:** CLI session bridge (Telegram/terminal sessions appear in the chat sidebar), session search, pin, archive.

**Backend changes (server.py):**
- Extend `GET /api/sessions` to include `source` field and CLI/gateway sessions from state.db
- `PATCH /api/sessions/{id}` → pin, archive, rename
- `GET /api/sessions/search?q=<term>` → FTS5 search over message content
- `GET /api/sessions/{id}/export` → Markdown transcript download

**Frontend changes (DC standalone patch):**
- Sessions panel: show CLI sessions with gold `cli` badge
- Search input at top of sessions list
- Per-session `⋯` menu: pin, archive, export, delete
- Pinned sessions float to top

**Effort:** Medium. state.db schema is already understood (used in galaxy/chat). Frontend is list manipulation patterns.

---

## Phase 6 — Voice Input

**What:** Microphone button in chat composer, Web Speech API transcription into the input field.

**Backend changes:** None.

**Frontend changes (DC standalone patch):**
- Add mic button next to the send button in the chat composer
- On click: `new SpeechRecognition()`, `continuous: false`, `interimResults: true`
- Interim results shown in the textarea in real-time
- Final result appended to existing textarea content
- Hide button if `!('SpeechRecognition' in window || 'webkitSpeechRecognition' in window)`

**Effort:** Low. ~50 lines of JS in a `_patch_standalone` block.

---

## Phase 7 — Mermaid Rendering

**What:** Code blocks with ` ```mermaid ` fence get rendered as diagrams in chat.

**Backend changes:** None.

**Frontend changes (DC standalone patch):**
- Load Mermaid.js from CDN (with SRI hash) in the standalone `<head>`
- In the chat message render function: after markdown rendering, scan for `<pre class="language-mermaid">` blocks and call `mermaid.render()`
- Fallback: if Mermaid fails, show the raw code block

**Effort:** Low. ~20 lines.

---

## What We Explicitly Skip

These are too deeply coupled to agent internals to port without months of work:

- **Approval cards** — requires `tools.approval` internals (private symbol imports)
- **Passkeys/WebAuthn** — nice to have, low priority vs the above
- **Full profile switching** — monkey-patches agent module-level paths at runtime; fragile
- **In-process AIAgent streaming** — requires wiring the full agent event loop (`run_agent.AIAgent`, turn lifecycle, session_lifecycle.py); not worth it when CLI streaming gives 90% of the UX win
- **Checkpoint/rollback panel** — requires the agent's shadow-git checkpoint layout
- **PTY terminal** — `api/terminal.py` from official is portable (easy), add in a future pass if wanted

---

## Recommended Order

1. **Phase 1 (streaming chat)** — biggest UX improvement, standalone backend change, no layout risk
2. **Phase 6 (voice)** — 1 hour, zero backend, high delight
3. **Phase 7 (mermaid)** — 1 hour, zero backend, useful
4. **Phase 3 (cron panel)** — high operational value, clean YAML API
5. **Phase 2 (workspace browser)** — high utility, medium frontend work
6. **Phase 4 (skills CRUD)** — improves daily workflow
7. **Phase 5 (session improvements)** — polish

---

## Staging Protocol (applies to all phases)

Per AGENTS.md + populate-phase pitfalls:
1. Write and test backend routes first (`curl` smoke test before any frontend work)
2. For each DC standalone patch: `node --check` the extracted component JS before restart
3. Gate each service restart separately — don't chain multiple phases into one restart
4. Keep `server.py.bak-<ts>` before any server.py edit
5. Visual verify via CDP screenshot after each phase, not just `curl`
