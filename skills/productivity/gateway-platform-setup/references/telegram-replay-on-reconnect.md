# Telegram replay-on-reconnect — reproduction trace

Real incident, traced from `~/.hermes/logs/agent.log`. The bot acted on a webui/sphere
instruction the user said they didn't send; investigation showed it WAS sent earlier in the
same session and got re-delivered.

## Timeline (one session, no full restart between these events)

```
20:10:34  inbound: "No detail panel when i click on it. Also, lets make the lines..."
20:10:44  /stop  → turn interrupted (reason=interrupted_during_api_call), offset NOT advanced
20:11:09  inbound: SAME "No detail panel..." text again  ← first duplicate (replay after /stop)
20:14:53  prior turn ends cleanly
20:16:20  Cached user photo img_6d37ecad7ae4.jpg
20:16:20  inbound: "i want to be able to seesmall sections of the sphere light up..."
          (legit photo+caption from the user's real chat 8878729385)
20:16:21  Session hygiene: auto-compressing 419 msgs / ~224,662 tokens
20:16:21  context compression started (messages=141)
20:16:48  context compression done (messages 141 -> 14)  ← in-RAM dedup history wiped
          → later reconnect re-delivers the 20:16 update as if new; agent re-acts on it
```

Two duplicates in one session (20:11 and the sphere replay), both around a state-disrupting
event (`/stop`, then context compaction).

## Why it happens

- Telegram long-poll acks updates by advancing `offset`. PTB keeps the offset in memory only;
  it is NOT persisted across in-process reconnects.
- On a transient network error or polling conflict, the gateway calls `start_polling(...,
  drop_pending_updates=False)`. Telegram then re-sends any update whose offset wasn't advanced.
- Context compaction (`agent.conversation_compression`) rewrites in-memory history
  (e.g. 141→14 msgs). The record that "update N was already handled" lives in that history, so a
  post-compaction replay is processed as brand-new.
- A `/stop` mid-turn interrupts before the offset advances → next poll re-delivers.

## The three call sites

```bash
grep -n "drop_pending_updates" /usr/local/lib/hermes-agent/gateway/platforms/telegram.py
# ~1468  _handle_polling_network_error  → False  (BUG: re-delivers on reconnect)
# ~1595  _handle_polling_conflict       → False  (BUG: same)
# ~2197  initial clean start_polling    → True   (correct: cold start drops backlog)
# ~2164  start_webhook                  → True   (webhook mode, correct)
# ~2177  delete_webhook                 → False  (clearing stale webhook, harmless)
```

## Fix (gated — agent source file)

Option A (minimal): flip the two reconnect sites (~1468, ~1595) to `drop_pending_updates=True`
so in-process reconnects discard backlog like the cold start. Tradeoff: a message sent during
the exact seconds-long reconnect blip is dropped. Acceptable because these are in-process
reconnects, not a gateway-down window. (Keep `False` ONLY where you genuinely want to catch
messages sent while the whole gateway was down — that is the initial cold start's job, and it
already uses `True`, so there's no path that needs `False` for that purpose here.)

Option B (no message loss): persist the last-seen `update.update_id` and pass it as explicit
`offset` to `start_polling` on reconnect, so Telegram resumes exactly where it left off without
replaying already-acked updates.

After editing: `systemctl --user restart hermes-gateway.service` (inside a gateway-hosted
session the `hermes gateway restart` CLI self-aborts on the loop guard), then watch the log for
`Connected to Telegram (polling mode)` and confirm no duplicate `inbound message` lines on the
next transient reconnect.

## Provenance-check commands (when a message looks rogue)

```bash
grep -n "inbound message" /root/.hermes/logs/agent.log | tail -40
grep -an "Cached user photo\|Flushing photo batch\|Starting Hermes Gateway\|Connected to Telegram\|context compression" /root/.hermes/logs/agent.log | tail -60
```
A line `inbound message: platform=telegram user=<name> chat=<real id>` is authentic at the
gateway layer. Authentic ≠ present intent — the replay bug makes an earlier-sent message
re-appear. Revert any action taken off the suspect message, THEN diagnose replay; never treat
platform attribution as proof the user meant it now.
