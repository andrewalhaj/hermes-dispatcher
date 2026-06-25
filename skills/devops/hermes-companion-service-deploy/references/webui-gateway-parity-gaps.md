# WebUI ↔ Gateway parity gaps & how to close them

The Hermes WebUI (`/root/projects/hermes-webui`) shares `~/.hermes` state with the
Telegram/Discord gateway but runs a **separate message loop**. Per-turn context
injection wired into the gateway does NOT automatically exist in the WebUI.

## The two inbound paths
- **Gateway (Telegram/CLI):** `/usr/local/lib/hermes-agent/gateway/run.py`
  — inbound handler builds `context_prompt`, then injects per-turn features
  (b-full RAG, message timestamps, process notifications) BEFORE calling the model.
- **WebUI:** `/root/projects/hermes-webui/api/streaming.py`, function
  `_run_agent_streaming` (~line 7058). Builds `_agent_msg_text` →
  `user_message = _build_native_multimodal_message(...)` → `agent.run_conversation(...)`.
  Anything the gateway injects must be added here too, or the WebUI is missing it.

## Gap found 2026-06-18: b-full per-turn RAG (cold-store auto-retrieval)
Gateway calls `_bfull_retrieve(message_text)` on every turn and appends ≥0.80
Supabase hits to the context (`run.py` ~line 9011). The WebUI did this **zero**
times — confirmed by grepping logs: WebUI b-full injections = 0, Telegram = 7.
Symptom: WebUI Hermes "feels dumber" because it gets no automatic knowledge
injection; it only has facts if it explicitly calls `knowledge.py search`.

### The fix (mirror the gateway in the WebUI loop)
Insert right after `_agent_msg_text` is assembled and BEFORE
`_build_native_multimodal_message`, in `_run_agent_streaming`:

```python
# B-full auto-retrieval (per-turn RAG) — mirrors gateway/run.py behaviour.
try:
    from gateway.run import _bfull_retrieve as _webui_bfull_retrieve
    _bfull_inject = _webui_bfull_retrieve(msg_text)
    if _bfull_inject:
        _agent_msg_text = _agent_msg_text + _bfull_inject
except Exception:
    pass
```

The `except: pass` is intentional — retrieval must never break a turn (same
contract as the gateway: `_bfull_retrieve` returns `''` on any failure/no-hit).
Backup `streaming.py` first, patch, then `systemctl restart hermes-webui` (GATED).

### Why the `gateway.run` import resolves at runtime (it's not on bare sys.path)
- The systemd unit sets `HERMES_WEBUI_AGENT_DIR=/usr/local/lib/hermes-agent` but
  NO `PYTHONPATH`.
- `api/config.py` (imported at the TOP of `streaming.py`, line ~25) appends
  `_AGENT_DIR` (`/usr/local/lib/hermes-agent`) to `sys.path` at module-load time.
- So by the time the lazy `from gateway.run import _bfull_retrieve` runs deep in
  the request, `gateway` is reachable. Pyright flags it as unresolvable — that's a
  static-analysis false positive; ignore it, it works at runtime.

## VERIFICATION PITFALL — `nsenter` gives a FALSE NEGATIVE
Do NOT verify the live process's import path with
`nsenter -t <pid> -m -- /proc/<pid>/exe -c "import sys; print(sys.path)"`.
That LAUNCHES A FRESH interpreter that bypasses `api/config.py`, so it shows a bare
stdlib-only sys.path and makes you think the import is broken. It isn't.

Verify correctly by reproducing the EXACT import chain the running process uses:
```bash
python3 -c "
import sys
sys.path.insert(0, '/root/projects/hermes-webui')
sys.path.append('/usr/local/lib/hermes-agent')
import api.config                                   # appends agent dir to sys.path
from gateway.run import _bfull_retrieve as r
print('bfull fired:', bool(r('mac studio serial number')))
"
```
A `True` here proves the patch will fire on the next real message. (Sending a real
message via curl is hard — WebUI auth is cookie-based, not HTTP Basic, so the
import-chain reproduction is the practical ground-truth check.)

## Gap found 2026-06-18: AGENTS.md / context files not loaded (context-cwd)
The gateway loads `AGENTS.md` (the hard-rules file) because `config.yaml`
`terminal.cwd: /root/.hermes` is bridged to `TERMINAL_CWD` at startup, and
`build_context_files_prompt` discovers `AGENTS.md` in that dir. The WebUI sets
`TERMINAL_CWD` to the **active workspace** (`/root/workspace`) per-session — which
has no `AGENTS.md` — so `resolve_context_cwd()` returned the workspace and the
agent ran WITHOUT its hard rules (WRITE GATE, recall gate, delegation reflex).

### The fix (pin context-file discovery to HERMES_HOME via the contextvar)
`agent/runtime_cwd.py` exposes `set_session_cwd()` which sets a thread-local
`_SESSION_CWD` contextvar that `resolve_context_cwd()` checks BEFORE `TERMINAL_CWD`.
In `_run_agent_streaming`, right before `_agent_kwargs = dict(...)` builds the
agent, pin it to hermes home:
```python
try:
    from agent.runtime_cwd import set_session_cwd as _set_session_cwd
    from hermes_constants import get_hermes_home as _get_hermes_home
    _session_cwd_token = _set_session_cwd(str(_get_hermes_home()))
except Exception:
    _session_cwd_token = None
```
The contextvar is context-scoped, so it only steers context-FILE discovery; actual
tool operations (write_file/terminal) still use the workspace `TERMINAL_CWD`. Verify
by rendering the prompt (see audit method below) and confirming `## AGENTS.md`
appears. Same Pyright false-positive on the imports — they resolve at runtime.

## Gap found 2026-06-18: session not auto-restored after `systemctl restart`
Two browser-side bugs made every WebUI restart drop the user on an empty page
(unlike the gateway, which the user never has to "follow up with" after a restart):
- **Cold-boot path (`static/boot.js` ~line 2202):** the boot catch-all did
  `localStorage.removeItem('hermes-webui-session')` on ANY `loadSession` error.
  A server mid-restart returns a network error / 5xx → ID wiped → next load empty.
  FIX: only wipe on a hard 404 (session truly gone): `if(e && e.status === 404) ...`.
- **Reconnect path (`static/ui.js`, `_recoverFromOfflineSoftly`):** when the offline
  banner cleared and `S.session` was null (tab idle during restart), nothing
  reloaded. FIX: when `!S.session`, read `localStorage.getItem('hermes-webui-session')`
  and `await loadSession(savedSid)`. These are JS/static files — no write gate, but
  the activating `systemctl restart hermes-webui` IS gated.

## DEFINITIVE parity audit method (render both prompts, diff them)
Don't audit parity by reading code paths and reasoning about them — that misses
silent gaps. Instead RENDER the actual assembled system prompt each surface
produces and `diff` them. This is the ground-truth check.

```bash
# WebUI side — replicate its startup: api.config (adds agent dir to sys.path) +
# the set_session_cwd patch + TERMINAL_CWD=workspace + platform='webui'.
/usr/local/lib/hermes-agent/venv/bin/python -c "
import sys, os
sys.path.insert(0, '/root/projects/hermes-webui'); sys.path.append('/usr/local/lib/hermes-agent')
import api.config
from agent.runtime_cwd import set_session_cwd
from hermes_constants import get_hermes_home
set_session_cwd(str(get_hermes_home()))
os.environ['TERMINAL_CWD']='/root/workspace'; os.environ['HERMES_SESSION_PLATFORM']='webui'
from run_agent import AIAgent
from agent.system_prompt import build_system_prompt
a=AIAgent(model='claude-sonnet-4-6',provider='anthropic',platform='webui',quiet_mode=True,session_id='audit-webui')
print(build_system_prompt(a))
" 2>&1 | grep -v 'bypass\|Transport\|Warning\|Loading\|weights\|HF_TOKEN\|rate' > /tmp/webui.txt

# Gateway side — TERMINAL_CWD=~/.hermes + platform='telegram'.
/usr/local/lib/hermes-agent/venv/bin/python -c "
import os; os.environ['TERMINAL_CWD']='/root/.hermes'; os.environ['HERMES_SESSION_PLATFORM']='telegram'
import sys; sys.path.append('/usr/local/lib/hermes-agent')
from run_agent import AIAgent
from agent.system_prompt import build_system_prompt
a=AIAgent(model='claude-sonnet-4-6',provider='anthropic',platform='telegram',quiet_mode=True,session_id='audit-tg')
print(build_system_prompt(a))
" 2>&1 | grep -v 'bypass\|Transport\|Warning\|Loading\|weights\|HF_TOKEN\|rate' > /tmp/tg.txt

diff /tmp/tg.txt /tmp/webui.txt
```
A CLEAN 1-to-1 match leaves exactly ONE expected diff: the platform hint line
(`PLATFORM_HINTS` in `agent/prompt_builder.py`) — Telegram's markdown/MEDIA guide
vs the WebUI's. That difference is CORRECT and intentional; don't try to erase it.
Everything else (SOUL.md, MEMORY.md, AGENTS.md, skills index, Honcho block, tool
guidance, profile hint, env hints, timestamp) must be byte-identical. If anything
else differs, that's a real gap — go close it with the method below.

NOTE: render-the-prompt-and-diff catches STABLE/CONTEXT/VOLATILE-tier gaps (system
prompt). It does NOT catch per-TURN injection gaps (b-full RAG, timestamps,
process notifications) — those are appended to the user message at request time,
not the system prompt. Audit BOTH: diff the system prompts (this method) AND diff
the per-turn injection points in `run.py` vs `streaming.py` (the method below).

## General method for any future parity gap
1. Identify the feature in `gateway/run.py`'s inbound handler.
2. Grep `streaming.py` for it — if absent, that's the gap.
3. Find the `_agent_msg_text`/`user_message` assembly point in `_run_agent_streaming`.
4. Mirror the injection with a defensive `try/except: pass`.
5. Verify via the import-chain reproduction (NOT nsenter), then gated restart.
