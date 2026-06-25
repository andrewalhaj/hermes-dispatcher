# Session Handoff — 2026-06-18
**Session:** 20260617_202348_0ce8de8f (WebUI)
**Duration:** ~6 hours
**Status:** Two open issues. Everything else stable.

---

## OPEN ISSUE 1: delegation STILL routes to DeepSeek (not the Studio)

### What we want
`delegate_task` children run on `qwen2.5-coder-14b-32k` on the Mac Studio
(`http://100.93.2.43:11434/v1`). This is 2.15× faster than the 32B on raw inference.

### What actually happens
Every `delegate_task` call returns `"model": "deepseek-v4-pro"`. The Studio
access log (`/tmp/ollama-error.log`) shows zero connections from the mini
(`100.113.100.81`) — the child never dials out to the Studio at all.

### Root cause chain (everything verified, none sufficient alone)
1. **`api_key_env: DEEPSEEK_API_KEY`** in delegation block → **REMOVED** ✓
2. **`context_length` not declared** for `qwen2.5-coder-14b-32k` in
   `custom_providers` → `get_custom_provider_context_length()` returned `None`
   → agent init queried Ollama live → got 32768 → **REMOVED**, now declares 65536 ✓
3. **`model.ollama_num_ctx`** not set → live Ollama query returns 32768 <
   `MINIMUM_CONTEXT_LENGTH` (64000) in `agent/model_metadata.py` →
   `_check_ollama_runtime_context` in `conversation_loop.py` fires a refusal
   message BEFORE any API call → child falls back to DeepSeek. Added
   `ollama_num_ctx: 65536` to top-level `model:` block → **DONE** ✓ ...but
   delegation STILL hits DeepSeek. The fix should work per code reading but
   doesn't in practice.

### What the code says should happen
- `agent_init.py` line 1617: `_ollama_num_ctx_override = _model_cfg.get("ollama_num_ctx")`
- If set → line 1620: `agent._ollama_num_ctx = int(65536)` → skips live query
- `conversation_loop.py` `_check_ollama_runtime_context`: 65536 ≥ 64000 → no refusal
- Yet delegation still returns `model: deepseek-v4-pro` after all fixes applied

### What to investigate in the new session
1. **Is `_model_cfg` the full config `model:` block or the delegation sub-block?**
   Run: `nsenter -t <gwpid> venv/bin/python -c "from agent.agent_init import init_agent; ..."` 
   and capture what `_model_cfg` actually is at runtime for a delegation child.
2. **Is there a SECOND `_check_ollama_runtime_context` call** somewhere after
   init that re-queries Ollama? Search: `grep -n "_check_ollama_runtime_context\|query_ollama_num_ctx" agent/conversation_loop.py`
3. **Run a child in a debug harness** with `HERMES_DEBUG=1` or by patching
   `conversation_loop.py` to log the `_ollama_num_ctx` value at runtime.
4. **Alternative fix: patch `query_ollama_num_ctx`** to return 65536 when the
   model name contains "coder-14b" — surgical, guaranteed to work, no config
   layer to misread.
5. **Nuclear option: `ollama_num_ctx` on the Modelfile itself** set to 131072
   so Ollama reports a native context ≥ 64k. Then no override needed.

### Current live config state
```yaml
model:
  default: claude-sonnet-4-6
  provider: anthropic
  ollama_num_ctx: 65536       # ← added this session, should set _ollama_num_ctx

delegation:
  model: qwen2.5-coder-14b-32k
  provider: custom:mac-studio
  base_url: http://100.93.2.43:11434/v1
  api_key: ''
  api_mode: chat_completions
  child_timeout_seconds: 900
  max_concurrent_children: 12
  # api_key_env: DEEPSEEK_API_KEY  ← REMOVED

custom_providers:
- name: mac-studio
  base_url: http://100.93.2.43:11434/v1
  models:
    qwen2.5-128k: {context_length: 131072}
    qwen2.5-32b-64k: {context_length: 65536}   # ← should be 32k, cleanup needed
    qwen2.5-coder-14b-32k: {context_length: 65536}
```

### Studio model state
```
qwen2.5-coder-14b-32k  9GB  ← delegation target (rebuilt this session)
qwen2.5-32b-32k       19GB  ← fallback / curator / compression (before Sonnet moves)
qwen2.5-32b-64k       19GB  ← ORPHAN, should be deleted
qwen2.5:72b           47GB  ← heavy tasks
```
VRAM at P=4: coder-14b resident at ~15GB (much lighter than 32B's 54GB).

---

## OPEN ISSUE 2: Kanban edit broken in WebUI

### Symptom
You reported "something broke after trying to edit the kanban board." Exact
visual broken state unknown — browser proxy (port 9377) was down, couldn't
inspect console.

### What we know
- **Backend: 100% clean.** All kanban API endpoints return 200:
  `GET /api/kanban/board`, `PATCH /api/kanban/tasks/{id}`, `POST /api/kanban/tasks`
- **JS: no parse errors.** `node --check static/panels.js` passes.
- **No server-side errors** in `journalctl -u hermes-webui`.

### What changed (likely cause)
The most recent git commit AND local uncommitted changes both touched kanban JS:

```
Commit 804e050d (your commit, Jun 17 21:33):
  style(kanban): status colors, stale stripes, hover-only actions, sidebar chips

Uncommitted local changes on top:
  static/panels.js: +45 lines (priority color helpers, avatar HTML, card metric icons)
  static/style.css: +81 lines (new kanban card styles)
  static/index.html: +3 lines (Google Fonts: Space Grotesk, IBM Plex Sans/Mono)
```

The uncommitted changes rewrote `_kanbanCard()` to add priority badges, avatars,
comment/link icons, and age spans. The **hover-only actions** from the commit
hide the quick-action buttons until hover — the Edit button on the card itself
may not be visible unless you hover.

### How to reproduce / verify
1. Open the kanban board in the WebUI
2. Open browser DevTools → Console (F12)
3. Click a card to open detail view
4. Look for the Edit button in the detail panel (not on the card itself)
5. If the modal doesn't open: check console for JS errors

### Fix path
If the JS has a runtime error: `git stash` to revert uncommitted changes,
then re-apply them carefully. If it's just the hover-only CSS hiding the edit
button on cards: the Edit button in the detail view (line 2887 of panels.js)
is in a different codepath and should still work.

---

## What was completed this session (stable changes)

### Infra / config
- **Studio P=4**: `OLLAMA_NUM_PARALLEL=4`, `OLLAMA_MAX_LOADED_MODELS=1`
  (applied via launchctl bootout+bootstrap — plain kill doesn't reload plist)
- **Vision → Sonnet**: `auxiliary.vision = claude-sonnet-4-6 / anthropic`
- **web_extract → Sonnet**: `auxiliary.web_extract = claude-sonnet-4-6 / anthropic`
- **compression → Sonnet**: `auxiliary.compression = claude-sonnet-4-6 / anthropic`
- **curator stays local**: `qwen2.5-32b-32k @ custom:mac-studio` (background cron, correct)
- **delegation model**: `qwen2.5-coder-14b-32k` (2.15× faster than 32B on raw inference)
- **max_concurrent_children**: 12 (was 8)
- **WebUI installed**: `hermes-webui` at `/root/projects/hermes-webui`, systemd-managed,
  bound to `0.0.0.0:8787`, accessible at `http://100.113.100.81:8787`
- **WebUI platform_disabled.webui**: same 51-skill suppress list as Telegram
- **AGENTS.md + SOUL.md**: warning preambles removed; delegation trigger corrected
  (no longer says "on DeepSeek")
- **MEMORY.md**: corruption fixed, delegation routing corrected

### Benchmarks (raw inference, not delegation)
| Model | Single eval | Prompt ingest | 4-wide aggregate | VRAM |
|---|---|---|---|---|
| qwen2.5-coder-14b-32k | **29.0 t/s** | **1595 t/s** | **41.3 t/s** | 15GB |
| qwen2.5-32b-32k | 13.5 t/s | 225 t/s | 19.3 t/s | 54GB |

The 14B is definitively 2.15× faster. If delegation can be made to route to it,
it's the right model for the Studio delegation target.

### Baseline files written
- `references/performance-baseline-pre-context-tuning-2026-06-17.md`
- `references/performance-baseline-p1-2026-06-18.md`
- `references/performance-baseline-p4-final-2026-06-17.md`
- `references/studio-delegation-findings-2026-06-18.md` (the full delegation debug saga)

### Critical pitfall discovered (in skill)
**launchctl plain-kill does NOT reload an edited plist.** KeepAlive respawns
from launchd's cached in-memory copy. The working pattern is:
```bash
launchctl bootout gui/501/com.ollama.server
sleep 2
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.ollama.server.plist
```
This is now documented in `skills/devops/ollama-inference-node-ops/SKILL.md`.

---

## Known orphans / cleanup needed
- `qwen2.5-32b-64k:latest` still on Studio (19GB, should be deleted)
- `qwen2.5-32b-64k: {context_length: 65536}` in `custom_providers` should be
  cleaned to `qwen2.5-32b-32k: {context_length: 32768}`
- Files written by subagents during debugging: `/root/.hermes/*.py` (palindrome,
  fizzbuzz, flatten, gcd, square, cube, is_even, clamp) — safe to delete

---

## Gateway restart note
The gateway has been restarted many times this session. Current state:
- PID: check with `XDG_RUNTIME_DIR=/run/user/0 systemctl --user show hermes-gateway -p MainPID --value`
- ha-bot gateway: also running, untouched
- Both healthy as of session end
