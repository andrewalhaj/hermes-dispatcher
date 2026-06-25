# Hermes Website (hermes.andrewskingdom.com) — Kanban + Panels Wiring

**Date:** 2026-06-19 · **Status:** Code DONE + verified on test instance 8788. AWAITING gated cutover restart.

## What this site is
- Public: https://hermes.andrewskingdom.com (cloudflared token tunnel, pid ~2250262) → local http://100.113.100.81:8787/
- Live service: `hermes-webui.service`, WorkingDirectory=`/root/projects/hermes-webui-new`, ExecStart=`venv/bin/python server.py`
- Serves `standalone.html` (759KB DC/bundler design prototype) patched per-request by `server.py`'s `_patch_standalone` + (NEW) `_patch_board_manifest`.
- The Kanban panel = `<dc-import name="Hermes Board v2">` — a DCLogic component bundled gzip+base64 INSIDE `__bundler/manifest` (NOT the template scripts). Decode: find board asset (mime endswith javascript, decoded text has "Hermes Board v2" + "extends DCLogic"), the component is `var J = "<escaped>"` in the asset wrapper.
- **The site reads `~/.hermes/kanban.db` — the SAME DB the agent's `kanban_*` tools write.** Wiring the board = dogfood: my `kanban_create` cards show live on the site.

## What was DONE (all in /root/projects/hermes-webui-new/server.py)
1. **Board seed**: `_patch_board_manifest` decodes board asset, patches `J` so `tasks`/`workers` seed from `window.__RD_KANBAN__`/`__RD_WORKERS__` (mock kept as `||` fallback), recompress+splice. Round-trip byte-stable (all 22 assets preserved, fonts byte-identical).
2. **Board data builders**: `_load_tasks()` enhanced (deps.children, ageSec, branch, desc, workerLog from run summaries, JSON-or-CSV skills parse). New `_workers_for_ui()` (profiles from task_runs + live running claims).
3. **Mutation endpoints**: PATCH `/api/kanban/tasks/{id}` (status+event, rejects running=400), POST `/api/kanban/tasks` (create→triage), POST `/api/kanban/tasks/{id}/comment`, PATCH `/api/kanban/tasks/{id}/desc`, POST `/api/kanban/dispatch` (real `hermes kanban dispatch --dry-run --json`, parses spawned[] len). Board JS move/add/comment/saveDesc/refresh/runDispatcher → fetch with optimistic UI + revert.
4. **LIVE SSE**: `/api/kanban/events/stream` rewritten — polls `_kanban_fingerprint()` (status/priority/assignee snapshot + comment/event/run counters) every 2s, pushes full board as SSE `board` event on ANY change (incl external CLI/dispatcher/agent writes). Board subscribes via EventSource in componentDidMount. VERIFIED: external DB write pushed to client ~2s, no refresh.
5. **Sessions panel**: was `showSessions: false` (dead). Patched → `s.panel === 'sessions'`. Data already wired to `__RD_SESSIONS__`.
6. **Settings persistence**: `/api/settings` GET/POST now persist to `webui_settings.json` (NOT gated config.yaml — POLA). Component seeds from `__RD_SETTINGS__`, debounced `_saveSetting` POSTs each change. setX→snake_case key map.

## Verification (test instance port 8788, NOT live)
- CDP screenshot: board renders real 20/20 tasks, 6 columns, real DM Voice Board titles/P8/P5/ages.
- Full CRUD against kanban.db: create→row(created_by=webui), move→persisted, comment→persisted, running→400.
- SSE live push proven.
- Settings persist+reload. Dispatch dry-run returns 0 + info.skipped_unassigned:2 (correct — ready tasks unassigned).
- All data panels real: memory/insights(625 sess)/skills(60)/logs/galaxy(601 nodes)/swarm(7).

## REMAINING (blocked)
- **Cutover**: live service still runs OLD server.py. `systemctl restart hermes-webui` (WRITE-GATED, blips chat ~5s) loads new code. Backup: `server.py.bak-kanban-wire-20260619050841`. Pre-cleared __pycache__.
- **Chat panel**: send()/sendChat() use `cannedReply()` hardcoded strings. Real wiring possible via `/root/projects/hermes-webui/api/streaming.py` (9000+ lines, has /api/chat/start+stream agent backend). BLOCKED on Andrew: which profile/model, shared-vs-isolated session w/ Telegram, security of tool-executing agent endpoint on public domain.
- **Agent sidebar roster** (main shell, not board): still shows mock names (rvc-runner/atlas-etl/npc-builder) — cosmetic, in main component, separate from board workers.

## Cutover procedure (when greenlit)
1. `rm -f /root/projects/hermes-webui-new/__pycache__/server.cpython-*.pyc`
2. arm gate + `systemctl restart hermes-webui`
3. Verify: `systemctl show hermes-webui -p ActiveEnterTimestamp -p MainPID` (timestamp MUST move), curl :8787 → 200, then curl https://hermes.andrewskingdom.com/ → 200, CDP board render, create a card via my kanban_* tools → confirm it appears live.
