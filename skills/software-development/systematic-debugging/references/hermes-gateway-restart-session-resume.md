# Hermes Gateway: restart / session-resume internals

Worked example for debugging "the gateway behaves wrong after a restart" — stale
messages reappearing, the agent acting on old requests, apparent amnesia.
Captured 2026-06-18 while root-causing two distinct restart symptoms.

## The two failure modes (don't conflate them)

### A. Telegram update REPLAY (transport layer)
**Symptom:** an old user message (including photo+caption) gets processed AGAIN
as if newly sent, after an in-process polling reconnect.

**Root cause:** `gateway/platforms/telegram.py` has THREE `start_polling` call
sites. Initial clean start uses `drop_pending_updates=True` (correct). The two
RECONNECT paths — `_handle_polling_network_error` (~line 1468) and
`_handle_polling_conflict` (~line 1595) — historically used
`drop_pending_updates=False`. PTB's offset (`Updater._last_update_id`) is NOT
persisted across the stop()/start_polling() cycle, and PTB's `stop()` is wrapped
in a try/except that swallows failures — so when the network is already broken,
the `get_updates(offset=last_id, timeout=0)` cleanup that ACKs fetched updates
never runs. Telegram then re-delivers those un-ACK'd updates on the next poll.

**Tell:** same inbound message logged twice, seconds-to-minutes apart, often
straddling a `/stop` or a network blip. Grep `agent.log` for duplicate
`inbound message: ... msg='<same text>'`.

**Fix:** both reconnect paths must use `drop_pending_updates=True` (committed
770448c5b, 2026-06-18). Re-delivering already-processed messages is far worse
than dropping a message that arrived during a sub-second reconnect blip.

### B. Pre-compaction user messages replayed as "pending" (session/history layer)
**Symptom:** after a restart, the agent latches onto a task the user raised
BEFORE the last context compaction, treating it as an outstanding request — even
though it was already handled. Looks like the agent "randomly brought up" old work.

**Root cause chain:**
1. Context compaction (`agent/context_compressor.py`) is FORCED to keep the most
   recent user message(s) in the protected "tail" via
   `_ensure_last_user_message_in_tail` (#10896). So those user messages get
   persisted in `state.db` physically BEFORE the `[CONTEXT COMPACTION — REFERENCE
   ONLY]` summary block.
2. On restart, `gateway/run.py::_build_gateway_agent_history` loads ALL active
   messages. Pre-compaction user messages come through as ordinary `role=user`
   rows with content → they land in `agent_history` looking like unanswered asks.
3. `_strip_interrupted_tool_tails` only strips TOOL tails. The auto-resume system
   note (`_is_resume_pending` branch, ~line 15273) only says "skip old TOOL calls"
   — it says nothing about pre-compaction USER messages.
4. Net: the compaction summary correctly says "answer only what's AFTER this
   block," but the stale user messages sit visually BEFORE it, and an ambiguous
   new message ("yes", "test") gets bound to the wrong pending request.

**Verification recipe (read-only, no restart needed):**
```python
import sqlite3
conn = sqlite3.connect('/root/.hermes/state.db')
# columns: id, session_id, role, content, ..., timestamp, ..., active
rows = conn.execute(
    "SELECT id, role, active, substr(content,1,80) FROM messages "
    "WHERE session_id=? ORDER BY id ASC", (SESSION_ID,)).fetchall()
# Look for role=user rows with active=1 appearing BEFORE the
# '[CONTEXT COMPACTION' assistant row. Those are the offenders.
```
Restored messages share near-identical timestamps (batch-inserted on resume) —
another tell.

**Proposed fix (pending greenlight at capture time):** in
`_build_gateway_agent_history`, track passing the `[CONTEXT COMPACTION` marker;
neutralize user messages that appear BEFORE it (replace content with a silent
placeholder) so alternation stays valid but the LLM won't treat them as pending.
Post-marker user messages are untouched.

## Boot-on-start gotcha
`hermes-gateway.service` runs under **user** systemd (`systemctl --user`), parent
PID is `systemd --user`. For it to start at boot WITHOUT a login session, user
lingering must be enabled: `loginctl show-user root | grep Linger` → `Linger=yes`.
`systemctl --user is-enabled hermes-gateway` alone is NOT sufficient proof of
boot-start; check lingering too. (System-wide `systemctl` will report the gateway
"not-found" because it's a user unit — don't conclude it's missing.)

## Process meta-lesson
Both fixes above were partly done in a PRIOR session and lost to compaction. The
working tree had the `drop_pending_updates=True` change with an explanatory
comment, but no commit — and the next session re-investigated it from scratch as
a mystery. ALWAYS `git diff` / read the live file / `session_search` before
declaring a Hermes-internal bug undiagnosed. See Phase 1 Step 0 in the parent skill.
