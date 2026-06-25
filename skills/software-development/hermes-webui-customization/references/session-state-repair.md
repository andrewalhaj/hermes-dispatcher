# Session State Repair — corrupted sessions, restart amnesia, memory corruption

Three distinct failure modes that all present as "the WebUI you is broken." Diagnose
which one you have FIRST — the fixes are completely different.

| Symptom | Logs | Cause | Fix |
|---|---|---|---|
| Messages send, no reply, silent | HTTP 400 `tool_use`/`tool_calls` | orphaned tool result in `state.db` | deactivate orphan row |
| New blank chat after restart, prior convo gone | clean | LRU agent cache wiped (by design) | `webui_prefill_messages_script` |
| Answers off / memory looks polluted | clean | `N\|` prefixes / stale `[HONCHO_DUP]` in MEMORY.md | `memory_sanitize.py` |

---

## 1. Corrupted session — the orphaned-tool_result HTTP-400 cascade

### Tell
`journalctl -u hermes-webui` shows, on every send to one session:
```
HTTP 400: messages.<N>: `tool_use` ids were found without `tool_result` blocks
  immediately after: toolu_XXXX. Each `tool_use` block must have a corresponding
  `tool_result` block in the next message.        # Anthropic
...
🔄 Primary model failed — switching to fallback: deepseek-v4-pro
HTTP 400: An assistant message with 'tool_calls' must be followed by tool messages
  responding to each 'tool_call_id'.              # DeepSeek fallback rejects it too
...
⚠️ Skipping session persistence for large failed session to prevent growth loop.
```
Both providers reject the ENTIRE message history, so the session is permanently dead
until repaired. In the browser this is SILENT — messages just pile up with no response.

### Root cause
A `role=tool` message whose `tool_call_id` matches NO `tool_calls[].id` in any active
assistant message. Happens when an assistant turn fires a parallel tool batch but only
ONE call gets recorded in the assistant row's `tool_calls` JSON, while BOTH tool results
land as separate `role=tool` rows. The second result is an orphan. (The Anthropic error
points at a message INDEX, not always the literal orphan — scan structurally, don't trust
the index.)

### Schema (state.db)
- `sessions` table — PK is `id` (NOT `session_id`). Has `message_count`, `source`, `system_prompt`.
- `messages` table — `id`, `session_id`, `role`, `content`, `tool_call_id`, `tool_calls`
  (JSON array of `{id, function:{name,...}}`), `active` (1/0). Inactive rows are excluded
  from the prompt but kept for the user to inspect.

### Diagnose — structural orphan scan (the reliable check)
```python
import sqlite3, json
db = sqlite3.connect("/root/.hermes/state.db"); db.row_factory = sqlite3.Row
SID = "<session_id>"
msgs = db.execute(
    "SELECT id,role,tool_call_id,tool_calls,active FROM messages "
    "WHERE session_id=? AND active=1 ORDER BY id ASC", (SID,)).fetchall()

declared = set()
for m in msgs:
    if m["role"] == "assistant" and m["tool_calls"]:
        for c in json.loads(m["tool_calls"]):
            if "id" in c: declared.add(c["id"])

orphans = [m["id"] for m in msgs
           if m["role"] == "tool" and m["tool_call_id"] not in declared]
print("orphaned tool results:", orphans)

# Also scan the inverse: assistant tool_calls with NO following tool result
i = 0
while i < len(msgs):
    m = msgs[i]
    if m["role"] == "assistant" and m["tool_calls"]:
        expected = {c["id"] for c in json.loads(m["tool_calls"]) if "id" in c}
        found = set()
        j = i + 1
        while j < len(msgs) and msgs[j]["role"] == "tool":
            found.add(msgs[j]["tool_call_id"]); j += 1
        missing = expected - found
        if missing: print("dangling tool_use at msg", m["id"], "missing", missing)
    i += 1
```

### Fix — deactivate the orphan (backup first)
The orphan's side-effect (the file write / command) ALREADY happened — dropping the row
loses nothing real, just the duplicate result record.
```python
import shutil, sqlite3
from datetime import datetime
shutil.copy("/root/.hermes/state.db",
            f"/root/.hermes/state.db.bak-{datetime.now():%Y%m%d-%H%M%S}")
db = sqlite3.connect("/root/.hermes/state.db")
db.execute("UPDATE messages SET active=0 WHERE id=?", (ORPHAN_ID,)); db.commit()
```
Re-run the scan → expect `orphaned tool results: []`. The session resumes normally on the
next send. If a dangling tool_use is the problem instead, deactivate the assistant row that
declared the unanswered call (or synthesize a stub tool result — deactivation is simpler/safer).

---

## 2. Restart amnesia — by design, not a bug

On `systemctl restart hermes-webui` the process dies and the in-process LRU agent cache
(`SESSION_AGENT_CACHE` in `api/streaming.py`) is wiped. A new agent is rebuilt per session
via `AIAgent(**_agent_kwargs)` and gets a CLEAN, CORRECT system prompt — MEMORY.md, USER.md,
SOUL.md, AGENTS.md, skills list, Honcho block all present (verified: a fresh `MemoryStore(...)
.load_from_disk()` returns all entries un-corrupted). What's MISSING is the prior
**conversation history**: the WebUI opens a new blank session; old sessions still exist in
the sidebar but you must click in manually (`api/session_recovery.py` notes restore is
"manual ... if their session was open through a server restart").

So "amnesia" = no conversation continuity, NOT lost memory/identity. Distinguish from #1:
restart-amnesia has CLEAN logs; corruption has 400s.

### Continuity fix — `webui_prefill_messages_script`
WebUI supports a startup script (config key `webui_prefill_messages_script`, env
`HERMES_WEBUI_PREFILL_MESSAGES_SCRIPT`) run at each new-session start. Its stdout becomes a
prefill: JSON `{"messages":[{"role":"user","content":"..."}]}` (validated roles
system/user/assistant) OR plain text (→ one user message). Output cap 262_144 bytes; also
budget-capped by `webui_prefill_context_max_chars` (default 12_000). Pattern: script queries
`state.db` for the most recent `source='webui'` session (excluding the one starting), pulls
the last few assistant/user turns, emits a "continuing from previous session: <summary>"
prefill. This is a config write → GATE it. Verify the script's stdout parses before wiring.

### Verify memory loads clean on a fresh agent (rules out #3 masquerading as #2)
```python
import sys, os; sys.path.insert(0, "/usr/local/lib/hermes-agent")
os.environ["HERMES_HOME"] = "/root/.hermes"
from tools.memory_tool import MemoryStore
s = MemoryStore(memory_char_limit=3000, user_char_limit=2250); s.load_from_disk()
print(len(s.memory_entries), len(s.user_entries))
print(s.format_for_system_prompt("memory")[:200])
```
`MemoryStore.__init__` takes ONLY `memory_char_limit` / `user_char_limit` (positional/kw),
NOT `memory_enabled` — passing the latter raises TypeError.

---

## 3. Memory-file corruption — line-number prefixes & stale dedup tags

### Tells (in MEMORY.md / USER.md, and therefore in a session's injected system prompt)
- Lines beginning `4|`, `9|`, `12|…` — read_file output (`N|content`) written back into the file.
- `[HONCHO_DUP: YYYY-MM-DD]` tags — the Memory Honcho Dedup cron's 2-stage soft-delete tags;
  legitimate during the ≥3-day grace window, stale (should be gone) after.

### Cause
A weak model (the local Studio aux model that runs the hourly Offload / daily Dedup crons)
edits MEMORY.md by `read_file` (gets `N|` prefixes) → reconstruct → `write_file`, faithfully
writing the line numbers back. Periodic + always line-number-shaped = cron, not a one-off.

### Fix — mechanical sanitizer (don't rely on prompt discipline alone)
`~/.hermes/scripts/memory_sanitize.py` strips `^\d+\|` prefixes and `[HONCHO_DUP]` tags
≥GRACE_DAYS (3) old; backs up `.bak-sanitize-<ts>` before writing; `--check` exits non-zero
if corruption present (no write); silent when clean. Wire as a frequent no-agent cron
(`*/30 * * * *`, deliver=local) so corruption survives ≤30 min regardless of which model
edited. Defense-in-depth, NOT a substitute for #2 cron-prompt hardening below.

### Cron-prompt hardening (the source-side half)
In every cron that edits MEMORY.md (Memory Offload, Memory Honcho Dedup):
- Add: "DO NOT use read_file to read MEMORY.md then write_file to save it — read_file adds
  `N|` line-number prefixes that corrupt the file. Use `cat` to read and the `patch` tool
  for targeted edits only."
- Add a post-write INTEGRITY CHECK step: run `memory_sanitize.py --check`; on non-zero,
  restore from the `.bak` just made and report failure instead of success.

### Note on the snapshot defense already in core
`tools/memory_tool.py:load_from_disk` runs `_sanitize_entries_for_snapshot` (threat-pattern
scan → `[BLOCKED: …]` placeholder) for prompt-INJECTION defense only — it does NOT strip
`N\|` prefixes or dedup tags. That's why the external sanitizer is needed. Patching that core
file would be gated and update-fragile; prefer the external script + cron hardening.
