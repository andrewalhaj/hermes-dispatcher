# Session-history replay on restart — trace + schema notes

Distinct from `telegram-replay-on-reconnect.md`. That one is Telegram's `getUpdates` offset
re-delivering an un-acked update. THIS one is Hermes reloading already-persisted `state.db` rows
after a restart and replaying pre-compaction user messages as live turns. The
`drop_pending_updates` fix does nothing for this path.

## How it manifests

After a gateway restart (e.g. two restarts at 22:38 and 22:45 in the incident), the session
auto-resumes. The model is handed a reconstructed history that includes user messages from
*before* the last compaction. Those look like unanswered requests. When a short ambiguous reply
(`yes`, `test`, `go`, `greenlight`) arrives, the model latches onto the most recent stale
request and executes it — in the incident, a WebUI "sphere" change the user had moved on from.

## DB evidence (the smoking gun)

Dumping `messages` for the session showed this order:

```
id=22728 role=user      active=1  '[IMPORTANT: Background process ... matched watch pattern "Application startup'
id=22729 role=user      active=1  "[The user sent an image~ ... sphere description"
id=22730 role=user      active=1  'Lets have all the lines be a soft white ... shorten the titles'
id=22731 role=assistant active=1  '[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted ...'
id=22732 role=user      active=1  'yes'
id=22733 role=assistant active=1  'Now wire _score_multiphase ...'
```

`22729`/`22730` (the stale sphere request) sit BEFORE the compaction marker `22731`. The summary
in `22731` says "respond ONLY to the latest user message AFTER this summary" — but the stale
messages are before it, so the guard text doesn't cover them. They are replayed verbatim by
`_build_gateway_agent_history` and read as pending.

## Why the messages are in the tail

`agent/context_compressor.py` deliberately keeps the most recent user/assistant turns out of the
summary so the active task is never lost:
- `_ensure_last_user_message_in_tail`  (fixes #10896)
- `_ensure_last_assistant_message_in_tail` (fixes #29824)

Correct behaviour for a live session. The bug is downstream: on RESTART those preserved tail
rows are replayed as fresh history without being marked as already-handled.

## The replay site

`gateway/run.py` → `_build_gateway_agent_history(history, ...)`. It iterates stored rows and:
- passes tool_calls / tool results through intact,
- strips auto-continue noise from user messages (`_strip_auto_continue_noise`),
- strips interrupted tool-call tails (`_strip_interrupted_tool_tails`),
- but replays every other `role=user` row's content verbatim.

No logic distinguishes user rows that predate a `[CONTEXT COMPACTION` marker. That's the gap.

## Fix shape

Inside the iteration, set a flag when a row's content starts with `[CONTEXT COMPACTION`. For
`role=user` rows seen BEFORE the flag is set, substitute a neutral placeholder
(`[earlier message — already handled, see compaction summary]`) instead of the raw text. Keeps
API message-alternation valid; removes the false pending-request signal. Post-marker user rows
unchanged. Revert = restore the function.

## Schema gotchas (so you don't waste time re-deriving)

- `state.db` `messages` columns: `id, session_id, role, content, active, timestamp`.
  There is **no `created_at`** column — querying it throws `OperationalError: no such column`.
  Order by `id ASC` (monotonic) or `timestamp`.
- `sessions` table has **no `compression_summary`** column. The compaction summary is just a
  normal `role=assistant` row in `messages` whose content begins `[CONTEXT COMPACTION`.
- Cron jobs are **NOT** in `cron.db` (that file is 0 bytes / no tables). They live in
  `~/.hermes/cron/jobs.json` as a dict keyed by job id. Use `hermes cron list` to browse, and
  read the JSON directly for full prompts/fields. There is no `cronjobs` SQLite table.
- Find the session id from the gateway log: lines `agent.turn_context: conversation turn:
  session=<id> ...` or `[<id>]` prefixes in `~/.hermes/logs/agent.log`.

## Boot-on-start verification (came up same session)

The main gateway runs under **user** systemd (`systemd --user`, parent PID is
`/usr/lib/systemd/systemd --user`), not system systemd — so `systemctl status hermes-gateway`
(system scope) finds nothing; use `--user`:
```bash
systemctl --user list-unit-files | grep hermes      # hermes-gateway.service → enabled
systemctl --user is-enabled hermes-gateway.service   # enabled = starts on boot
loginctl show-user root | grep -i linger             # Linger=yes → user units run at boot w/o login
```
Both `enabled` AND `Linger=yes` are required for true start-on-boot. If enabled but linger is
off, the unit only starts on interactive login — `loginctl enable-linger <user>` fixes it.
