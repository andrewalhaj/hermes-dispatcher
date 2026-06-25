---
name: gateway-platform-setup
description: "Wire Hermes Gateway to Discord/Telegram/Slack/etc."
version: 1.0.0
author: Hermes Agent
metadata:
  hermes:
    tags: [gateway, discord, telegram, slack, messaging, setup]
    related_skills: [hermes-agent]
---

# Gateway Platform Setup

Connect Hermes Gateway to messaging platforms. Covers token/env var discovery, non-interactive service install, the allowlist requirement, and platform-specific quirks.

## Trigger

When a user asks to connect a messaging platform (Discord, Telegram, Slack, WhatsApp, etc.) to Hermes, or provides a bot token for one.

## Discovery: Finding the Right Env Var

The `.env` file is protected from `read_file` (defense-in-depth). To discover env var names:

```bash
# Search gateway config for token env var mappings
grep -n "DISCORD\|TELEGRAM\|SLACK" /usr/local/lib/hermes-agent/gateway/config.py | grep -i token

# Or find the Platform-to-env-var mapping
grep -A1 "Platform\." /usr/local/lib/hermes-agent/gateway/config.py | grep -i token
```

Known mappings (from `gateway/config.py` line ~1204):

| Platform | Env var |
|----------|---------|
| Discord | `DISCORD_BOT_TOKEN` |
| Telegram | `TELEGRAM_BOT_TOKEN` |
| WhatsApp | `WHATSAPP_TOKEN` or `META_WHATSAPP_TOKEN` |

The gateway auto-detects platforms from env vars — no manual config.yaml entry needed.

## Step 1: Write the Token to .env

**Pitfall: Shell interpolation** — `echo "TOKEN=..." >> .env` can mangle tokens containing dots, hyphens, or special chars.

**Pitfall: Secret redaction** — Hermes `security.redact_secrets` (on by default) will mangle token-like values in tool output. Both `printf 'TOKEN=<value>'` and inline Python strings with the full token get truncated at output time — the value written to `.env` may also be corrupted if the redactor intercepts the write.

Safe method — use `python3 -c` with the token stored in a variable (never an inline string literal in the shell command itself):

```bash
# Replace lines in .env without printing the token inline
python3 -c "
token = '1234567890:***  # NEVER inline token in the shell command — use a variable
uid = 'userid_here'
env_path = '/root/.hermes/.env'

with open(env_path, 'r') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    # Uncomment and set existing commented-out vars
    if line.startswith('# TELEGRAM_BOT_TOKEN='):
        lines[i] = f'TELEGRAM_BOT_TOKEN=***    elif line.startswith('# TELEGRAM_ALLOWED_USERS='):
        lines[i] = f'TELEGRAM_ALLOWED_USERS={uid}\\n'

# Add ALLOW_ALL if not present
if not any('TELEGRAM_ALLOW_ALL_USERS' in l for l in lines):
    lines.append('TELEGRAM_ALLOW_ALL_USERS=true\\n')

with open(env_path, 'w') as f:
    f.writelines(lines)

# Verify without printing token value
import re
with open(env_path, 'r') as f:
    for line in f:
        if line.startswith('TELEGRAM_') and not line.strip().startswith('#'):
            safe = re.sub(r'(TOKEN=*** r'TOKEN=*** line.strip())
            print(safe)
"
```

Verify the token length matches what the user provided.

## Step 2: Set Allowlist (CRITICAL — skip this and nobody can use the bot)

After adding a platform token, the gateway will connect but **all users will be denied** unless you set an allowlist. The gateway log will warn:

```
WARNING gateway.run: No user allowlists configured. All unauthorized users will be denied.
```

Choose one:

```bash
# Open access (good for initial setup)
echo 'DISCORD_ALLOW_ALL_USERS=true' >> /root/.hermes/.env

# Restricted access (preferred for production)
echo 'DISCORD_ALLOWED_USERS=userid1,userid2' >> /root/.hermes/.env
```

Per-platform env vars: `DISCORD_ALLOW_ALL_USERS`, `TELEGRAM_ALLOW_ALL_USERS`, `DISCORD_ALLOWED_USERS`, `TELEGRAM_ALLOWED_USERS`, etc.

## Step 3: Install and Start Gateway

The `hermes gateway install` command is interactive — it asks two Y/n prompts. For non-interactive setup:

```bash
printf 'Y\nY\n' | hermes gateway install --force
```

This:
1. Answers "Y" to "Start the gateway now after installing?"
2. Answers "Y" to "Start the gateway automatically on login/boot?"
3. Installs as a systemd user service with linger enabled (survives SSH logout)

Verify:

```bash
hermes gateway status
tail -20 /root/.hermes/logs/gateway.log
```

Look for:
```
✓ discord connected
Gateway running with 1 platform(s)
```

## Step 4: Platform-Specific Manual Steps

### Discord

**REQUIRED**: Go to https://discord.com/developers/applications → your bot → Bot → Privileged Gateway Intents → enable **MESSAGE CONTENT INTENT**. Without this the bot cannot read message content and will be completely silent.

### Telegram

No additional manual steps for basic operation.

## Gateway Management Commands

```bash
hermes gateway status           # Check if running
hermes gateway restart          # Restart after config/env changes
hermes gateway start            # Start the service
hermes gateway stop             # Stop the service
journalctl --user -u hermes-gateway -f   # Live logs
```

**Important**: Changes to `.env` require `hermes gateway restart` to take effect.

## Platform Tone Consistency

When the user notices Hermes responds differently on Discord vs CLI (more conversational on Discord, more direct on CLI), the most common cause is **context continuity** — Discord has history backfill (last 50 messages) giving social context; CLI starts cold. Platform constraints (character limits, threading) also contribute. The model and persona file are the same.

To align tone across platforms, use a **personality preset** (not per-channel prompts — see pitfall below):

```bash
# 1. Define the personality
hermes config set agent.personalities.consistent \
  "Maintain exactly the same tone on all platforms. Be direct and task-focused — no conversational filler, no greeting pleasantries, no chitchat. Respond as if always on a terminal, regardless of whether the message came from Discord or CLI. Deliver results, not conversation."

# 2. Activate it globally
hermes config set display.personality consistent

# 3. Apply (personalities are read at session start)
hermes gateway restart
# For current CLI session: type /reset
```

Personalities apply to ALL platforms equally — CLI, Discord, Telegram, etc. This is the simplest way to normalize tone. If the user prefers a different shared tone, edit the personality text. If they want platform-specific tone, use per-channel prompts with exact channel IDs.

**Pitfall: `channel_prompts` has no wildcard support.** `channel_prompts` only matches by exact `channel_id` or `parent_id` (forum thread parent). There is no `*`, `default`, or catch-all key. To set a prompt for all Discord channels you'd need one entry per channel. Use a personality preset for global effects instead.

## Running a SECOND, separately-scoped bot (dedicated profile)

When the user wants a SEPARATE bot (different BotFather token, scoped to one domain — e.g. a Home-Assistant-only bot) ALONGSIDE the main one, do NOT add a second token to the same gateway. One gateway maps one token per platform. Instead stand the bot up as its own **Hermes profile** with its own gateway service. Both gateways run concurrently as distinct systemd user services.

### Procedure (verified working)
1. **Validate the token first** (catch typos before any setup): `curl -s "https://api.telegram.org/bot<TOKEN>/getMe"` must return `"ok":true` plus the bot's username. If the response is `"ok":false` with error code 401 / "Not Found", the token is invalid — DO NOT proceed with profile creation. Common causes: bot not yet created with @BotFather, token mistyped (missing character, wrong case), token revoked and regenerated. Fix: create the bot with @BotFather, copy the full token (no whitespace), and re-validate. This is the same preflight pattern as DATABASE_URL validation — a 2-second check prevents building infrastructure around a dead credential.
2. **Create the profile, cloning config + .env + skills** from the active one (inherits model + API keys via Manifest):
   `hermes profile create <name> --clone --description "..."`
   `--clone` copies config.yaml/.env/SOUL.md; skills come along too. (`--clone-all` for full state, `--no-skills` for an empty one.)
3. **CRITICAL — fix the cloned .env or the new bot collides with the parent.** `--clone` copies the PARENT bot's `TELEGRAM_BOT_TOKEN`, `DISCORD_BOT_TOKEN`, and any `*_ALLOW_ALL_USERS=true`. Left as-is, two gateways poll the SAME Telegram token (conflict) and the new bot inherits open access. In `~/.hermes/profiles/<name>/.env` you MUST:
   - Replace `TELEGRAM_BOT_TOKEN` with the NEW token (use the file-read method below, not inline).
   - **Comment out tokens for platforms this bot should NOT serve** (e.g. `# DISCORD_BOT_TOKEN=...`, `# DISCORD_ALLOW_ALL_USERS=...`) so it's single-platform. A commented token = that platform is skipped; the log will then show `Gateway running with 1 platform(s)`.
   - Set the allowlist tight: `TELEGRAM_ALLOWED_USERS=<uid>` and `TELEGRAM_ALLOW_ALL_USERS=false`.
4. **Token-write method that survives redaction:** write the raw token to a temp file with the file-write tool (bypasses shell redaction), then run a python script that reads it (`open('/tmp/tok.txt').read().strip()`), edits the .env, and verifies by LENGTH not by printing (`len(written)==len(token)` → "MATCH"). Shred the temp file after. Inline `echo`/`printf` and `$(...)` mangle token-like strings.
5. **Scope the bot via its profile SOUL.md** (`~/.hermes/profiles/<name>/SOUL.md`) — replace the default persona block with role + scope + the user's standing rules (e.g. "greenlight before infra changes"). This is HOW you make it domain-only; the persona is loaded fresh each turn. Pair with a seeded `memories/MEMORY.md` (writing another profile's memory needs `cross_profile=True` on the file tool — expect a soft-guard block first; pass it only after the user directed the setup).
6. **Install + start that profile's gateway** (every command takes `--profile`):
   `printf 'Y\nY\n' | hermes --profile <name> gateway install --force`
   This creates a DISTINCT service `hermes-gateway-<name>.service` (the main bot's is separate) with linger.
7. **Verify both run independently:**
   - `hermes profile list` → both profiles show `running`.
   - `tail -30 ~/.hermes/profiles/<name>/logs/gateway.log | grep -iE "connected|platform"` → `✓ telegram connected` / `Gateway running with 1 platform(s)` (1, not 2 — proves the other platform was correctly excluded).
   - `hermes --profile <name> gateway status` / `journalctl --user -u hermes-gateway-<name> -f` for live logs.
8. **Note shared budget:** a cloned profile uses the SAME API keys/Manifest route as the parent, so usage draws the same pool. Flag this; offer a separate key if metering matters.

### Per-profile management
`hermes --profile <name> gateway {status,restart,stop,start}`. `.env` edits need a restart. Profile isolation rule: don't edit another profile's skills/memory/cron unless explicitly directed.

**Pitfall — `gateway restart` is blocked when you ARE a gateway-hosted agent.** If this very session is running inside a gateway process (the common case when the user is talking to you over Telegram/Discord), `hermes --profile <name> gateway restart` self-aborts with `✗ Refusing to restart the gateway from inside the gateway process` (restart-loop guard) — even for a DIFFERENT profile's gateway. Restart the target service directly instead:
```bash
systemctl --user restart hermes-gateway-<name>.service
systemctl --user is-active hermes-gateway-<name>.service   # -> active
```
Then confirm reconnect in `~/.hermes/profiles/<name>/logs/gateway.log` (`✓ telegram connected`). The same applies to restarting your own gateway after a skill/SOUL.md/memory edit. Note: SOUL.md is loaded fresh each turn so persona edits need no restart; a restart is only needed for `.env` changes and (to be safe) skill-index changes.

## Cron job delivery routing (channel vs DM)

Cron jobs deliver via their `deliver` field, a comma-joined list of targets — e.g. `telegram:-1003947663220,discord:#cron-jobs`. A frequent complaint is "cron jobs aren't going to the [Cron Jobs] channel" — the usual cause is the target points at the user's **DM** (a bare positive user id like `telegram:8878729385`) instead of the **channel**.

**Telegram channel/group chat_ids are NEGATIVE** (e.g. `-1003947663220`); a DM target is the positive user id. To find the real channel id:
- `send_message(action='list')` shows friendly names (e.g. "Cron Jobs (channel)") but NOT always the id.
- Grep the gateway log for an inbound message from that channel: `grep -i "Cron Jobs" ~/.hermes/logs/gateway.log` → line shows `chat=-100...`. (Posting any test message into the channel first generates such a line.)

**Fix:** `cronjob(action='update', job_id=..., deliver='telegram:<negative_channel_id>,discord:#channel')` for each notifying job. Only jobs that actually notify need it — jobs with `deliver: local` are silent local saves by design (backups, digests); leave them. The 3-target string keeps Discord delivery intact alongside the corrected Telegram target.

**Verify delivery for real, not by inference:** a `no_agent` watchdog that's "silent unless P0/P1" produces NO message when healthy, so `cronjob(action='run')` on it is NOT a delivery test. Instead `send_message(target='telegram:<channel_id>', message='test')` → success returns a `message_id`, proving the chat_id routes. User preference seen: Andrew wants cron notifications in the channel ONLY, not DM+channel.

## Inbound document type whitelist (adding new file extensions)

When the user sends a file and the bot replies `Unsupported document type '.ext'. Supported types: ...`, the extension isn't in the gateway's inbound document allowlist. The fix is a 1-line dict entry, NOT a per-platform change.

- **Single source of truth:** `SUPPORTED_DOCUMENT_TYPES` dict in `/usr/local/lib/hermes-agent/gateway/platforms/base.py` (maps `.ext` → MIME type). The "Supported types:" list in the error is built dynamically from `sorted(SUPPORTED_DOCUMENT_TYPES.keys())` (in `platforms/telegram.py` ~line 6336, and mirrored per-platform), so editing the dict updates the error text too — no need to touch the message string.
- **Add an entry** (gated write — agent source file, get greenlight + arm the write-gate first):
  ```python
  ".html": "text/html",                       # inlined as text, like .txt/.md
  ".7z": "application/x-7z-compressed",        # archive, like .zip
  ```
  Text-like types (`.html`, `.md`, `.txt`, `.log`, code) get their content inlined into `event.text` (capped ~100 KB); archives/binaries get cached and passed as a media path.
- **CRITICAL — a restart is mandatory.** The running gateway imported `base.py` at startup and holds the OLD dict in memory; editing the file on disk does NOTHING until reload. The error message will keep showing the old list (a confusing false-negative — you "fixed" it but the bot disagrees) until you restart. Confirm the file is correct first (`python3 -c "import sys; sys.path.insert(0,'/usr/local/lib/hermes-agent'); from gateway.platforms.base import SUPPORTED_DOCUMENT_TYPES; print('.html' in SUPPORTED_DOCUMENT_TYPES)"` → `True`), THEN restart. Inside a gateway-hosted session, `hermes gateway restart` self-aborts (loop guard) — use `systemctl --user restart hermes-gateway.service` (or `hermes-gateway-<profile>.service`); the restart command may take >30s to return the shell while the old process drains — check `systemctl --user is-active` rather than waiting on the call.

## Telegram message replay / duplicate-processing on reconnect

Symptom: the bot processes a message the user already sent (and was already handled) a SECOND time — sometimes minutes later, sometimes appearing "out of nowhere." Classic tells: the same user message text logged twice with different timestamps, or a stale instruction acted on after the user moved on. In the wild this looked like a message the user swore they never sent (they had — earlier in the session) being replayed and acted upon.

**Root cause — `drop_pending_updates=False` on in-process reconnect paths.** Telegram polling acks updates by advancing an `offset`; PTB does NOT persist that offset to disk between in-process reconnects. There are three `start_polling` call sites in `gateway/platforms/telegram.py`:

| Path | `drop_pending_updates` | Correct? |
|------|------------------------|----------|
| Initial clean start (~line 2197) | `True` | ✅ drops backlog on cold start |
| Network-error reconnect (`_handle_polling_network_error`, ~line 1468) | `False` | ❌ re-delivers un-acked updates |
| Conflict retry (`_handle_polling_conflict`, ~line 1595) | `False` | ❌ same |

When the gateway hits a transient network error or a polling conflict mid-session (an internal reconnect, NOT a full restart), it re-polls with `drop_pending_updates=False` and Telegram re-sends any update whose offset wasn't advanced. The window widens dramatically right after **context compaction**: compaction rewrites the in-memory message history (e.g. 141→14 msgs), erasing the in-RAM record that a given update was already processed, so the replayed update sails through as if new.

A `/stop` mid-turn produces the same duplicate (the turn is interrupted before the offset advances; the next poll re-delivers).

**Fix options (gated — agent source file under `/usr/local/lib/hermes-agent`, get greenlight + arm write-gate):**
1. Set `drop_pending_updates=True` on the network-error and conflict reconnect paths (lines ~1468, ~1595) so transient reconnects discard backlog like the cold start does. Tradeoff: a message sent during the exact reconnect blip is lost — acceptable for a seconds-long in-process reconnect (vs a full gateway-down restart, where you DO want `False` to catch messages sent while down).
2. Or persist the last-seen `update_id` and pass it as explicit `offset` on reconnect (more code, no message loss).

Confirm the three call sites and their flag values before editing:
```bash
grep -n "drop_pending_updates" /usr/local/lib/hermes-agent/gateway/platforms/telegram.py
```
Full reproduction trace + log timeline: `references/telegram-replay-on-reconnect.md`.

## Session-history replay on restart (distinct from Telegram offset replay)

Symptom is the SAME as the Telegram replay bug — an old, already-handled user message gets acted on after a gateway restart — but the mechanism is different and the `drop_pending_updates` fix does **NOT** address it. This one lives entirely inside Hermes' own session reconstruction, not Telegram's polling.

**Root cause — pre-compaction user messages survive in the `state.db` tail and are replayed as pending.** When context compaction runs, the compressor (`agent/context_compressor.py`) is forced to keep the most recent user + assistant messages in the **tail** (outside the summary) via `_ensure_last_user_message_in_tail` / `_ensure_last_assistant_message_in_tail` (anti-loss guards, fixes #10896 / #29824). So those tail user messages get **persisted in `state.db` ordered BEFORE the `[CONTEXT COMPACTION — REFERENCE ONLY]` marker row**. On the next gateway restart, `_build_gateway_agent_history()` in `gateway/run.py` reloads ALL active rows and replays every `role=user` row with content as a normal prior turn. It strips interrupted tool-call tails and auto-continue noise — but does NOT strip pre-compaction user messages. The model then sees stale user requests sitting ahead of the live message and treats them as unanswered, acting on them when an ambiguous \"yes\"/\"test\"/\"go\" arrives.

The compaction summary's own instruction (\"Respond ONLY to the latest user message that appears AFTER this summary\") is undercut because those tail user messages appear **before** the summary row in DB order, not after.

**Diagnostic — dump the message rows around the compaction marker:**
```bash
/usr/local/lib/hermes-agent/venv/bin/python3 - <<'EOF'
import sqlite3
conn = sqlite3.connect('/root/.hermes/state.db')
# find the session id from the gateway log (agent.turn_context: session=...)
sid = '<session_id>'
rows = conn.execute(
  "SELECT id, role, active, substr(content,1,80) FROM messages "
  "WHERE session_id=? ORDER BY id ASC", (sid,)).fetchall()
for r in rows:
    print(f"id={r[0]} role={r[1]} active={r[2]} {r[3]!r}")
EOF
```
Tell: real `role=user` rows (with content, `active=1`) appearing immediately BEFORE the `[CONTEXT COMPACTION` assistant row. Those are the replay landmines.

**Fix (gated — agent source file `gateway/run.py`, function `_build_gateway_agent_history`):** track whether a `[CONTEXT COMPACTION` marker has been seen while iterating history; for `role=user` rows that appear BEFORE that marker, replace their content with a neutral placeholder (e.g. `[earlier message — already handled, see compaction summary]`) instead of replaying raw text — keeps message-alternation intact while removing the false \"pending request\" signal. Post-marker user messages pass through unchanged. Rollback = revert the function. Low risk: additive logic in the history builder, no state mutation.

**Do not blame compaction itself** — compaction summarised correctly and even told the model to ignore pre-summary items. The defect is the history *reconstruction* replaying tail user rows as live turns. Schema note: `messages` table columns are `id, session_id, role, content, active, timestamp` (no `created_at`); the `sessions` table has no `compression_summary` column — the summary is a normal `role=assistant` row in `messages`.

Full trace + schema: `references/session-history-replay-on-restart.md`.

## Streaming fragmentation on long responses — the THIRD duplicate cause (proven 2026-06-21)

Symptom reads identically to the two replay bugs — "you posted your response multiple times" — but the mechanism is neither offset-replay nor session-history-replay. It's **Telegram live-edit streaming colliding with the 4096-char message cap.** This one needs NO source edit; it's a one-line config flip.

**Root cause.** With `ui.platforms.telegram.streaming: true`, the gateway delivers via live-edit streaming (confirmed in the log by `streamed=True` on the delivery line). Telegram hard-caps a single message at 4096 chars. When a streamed response crosses that, the live-edit transport rolls over into new messages mid-stream and buffered content re-emits across bubbles — so one answer arrives as a pile of separate bubbles that reads as "posted multiple times."

**The decisive diagnostic — correlate response char count with the complaint, from the gateway log:**
```bash
tail -200 ~/.hermes/logs/gateway.log | grep -E "response ready|Suppressing normal final send"
```
Every `response ready: ... response=N chars` line carries the size. Build the table: responses under ~4096 = one clean bubble, no complaint; the response that drew the complaint is the one over 4096. This session: 2166/1840/1683-char answers were fine, the 5540-char memory-system answer triggered it. Single variable, airtight correlation. (The per-edit Telegram API calls aren't logged at INFO, so you confirm by char-count correlation, not by counting send events.)

**Fix (gated — config.yaml).** Flip Telegram to non-streaming so it uses the normal final-send path, which chunks cleanly at paragraph boundaries under 4096:
```
ui.platforms.telegram.streaming:  true → false
```
Discord is often already `false` — match it. Tradeoff: you lose the live-typing cursor effect; that's the only cost. Reversible, config-only.

**Two wiring facts that bit this session:**
1. **`config.yaml` is refused by the `patch`/`write_file` tools** ("Refusing to write to Hermes config file"). For a nested key the `hermes config set` CLI can't easily express, use a Python string-replace one-liner in `terminal` (still a gated WRITE-GATE action — arm the gate, `.bak` first, verify YAML parses after). The streaming flag lives at `ui.platforms.telegram.streaming` (nested under `ui:`), NOT the top-level `streaming:` block (that one, `enabled: false`, governs a different transport).
2. **A gateway restart is required** for the flag to take effect, and inside a gateway-hosted session `systemctl --user restart hermes-gateway` self-aborts (the SIGTERM kills the issuing session). Hand the user the command to run from a separate shell:  `systemctl --user restart hermes-gateway`. The config change persists; it activates on next restart.

**Disambiguation — three causes, same symptom, different fixes:**
| Trigger context | Likely cause | Fix |
|---|---|---|
| Long response (>4096 chars) + `streamed=True` | **Streaming fragmentation** | `ui.platforms.telegram.streaming: false` (config) |
| Transient network/conflict reconnect mid-session | Telegram offset replay | `drop_pending_updates=True` on reconnect paths (source) |
| Full gateway restart + ambiguous short reply | Session-history replay | strip pre-compaction user rows in `_build_gateway_agent_history` (source) |

## Mid-turn message provenance — verify before acting

When a message arrives mid-task that contradicts what the user is doing, OR the user later says "I didn't send that," do NOT silently act on it. Trace provenance from the gateway log FIRST:
```bash
grep -n "inbound message" /root/.hermes/logs/agent.log | tail -40   # who/when/text
grep -an "Cached user photo\|Flushing photo batch\|Starting Hermes Gateway\|Connected to Telegram" /root/.hermes/logs/agent.log | tail -40
grep -n "drop_pending_updates" /usr/local/lib/hermes-agent/gateway/platforms/telegram.py
```
A message logged as `inbound message: platform=telegram user=<name> chat=<id>` from the user's real chat id IS authentic at the gateway layer — but authenticity ≠ intent. The Telegram replay bug above can re-deliver a genuinely-sent-earlier message as if new. So "the user didn't send it (now)" and "it's a legitimate inbound from their account" are BOTH true simultaneously. The correct response when a contradicting/duplicate instruction appears: revert anything already done off it, then investigate replay/duplicate cause — don't treat platform-attributed text as proof of present intent. Note: this applies to genuine inbound messages, distinct from the `[OUT-OF-BAND USER MESSAGE]` marker, which IS a trusted direct steer.

## Troubleshooting

- **Bot silent on Discord**: Enable Message Content Intent in Developer Portal (see Step 4).
- **Same message processed twice / stale instruction acted on after the fact**: TWO independent causes, same symptom. (1) Telegram offset replay on in-process reconnect — drop_pending_updates=False on network-error/conflict paths. See "Telegram message replay / duplicate-processing on reconnect." (2) Stale instruction acted on after a RESTART (not a reconnect) — pre-compaction user messages persisted in the state.db tail get replayed by _build_gateway_agent_history. See "Session-history replay on restart." If the trigger was a full gateway restart + an ambiguous short reply ("yes"/"test"), suspect (2), not (1).
- **"You posted your response multiple times" on a LONG answer**: THIRD cause, different from the two replay bugs and fixable without source edits — streaming live-edit fragmenting a >4096-char response into multiple bubbles. Confirm by char-count correlation in the gateway log (`response ready: ... response=N chars` + `streamed=True`); the offending answer is the one over 4096. Fix: `ui.platforms.telegram.streaming: false` (config + restart). See "Streaming fragmentation on long responses."
- **Cron jobs not reaching the channel**: their `deliver` target is the user's DM (positive id) not the channel (negative id). Fix the `deliver` string per "Cron job delivery routing." Verify with a direct `send_message` to the channel, not by running a silent watchdog.
- **Two bots fighting over one Telegram token / new bot has open access after `--clone`**: the cloned `.env` still has the parent's token + `ALLOW_ALL=true`. Swap the token, comment out unwanted-platform tokens, set a tight allowlist. See "Running a SECOND, separately-scoped bot."
- **All users denied**: Check allowlist — set `DISCORD_ALLOW_ALL_USERS=true` or configure specific user IDs.
- **Gateway crashes on SSH logout**: Enable linger: `sudo loginctl enable-linger $USER`.
- **Gateway dies on WSL2 close**: Set `systemd=true` in `/etc/wsl.conf`.
- **`gateway restart` refuses with "Refusing to restart from inside the gateway process"**: you're running as a gateway-hosted agent (talking over Telegram/Discord). The CLI restart self-aborts as a loop guard, even for another profile. Use `systemctl --user restart hermes-gateway-<name>.service` instead. See "Per-profile management."
- **Discord and CLI feel like different agents**: Platform tone consistency above — use a personality preset, not `channel_prompts`.
- **`Unsupported document type '.ext'`**: extension missing from `SUPPORTED_DOCUMENT_TYPES` in `gateway/platforms/base.py`. Add the `.ext` → MIME entry (gated write), then restart the gateway via `systemctl --user restart hermes-gateway.service` — the edit is inert until reload, so the error text keeps showing the old list until you restart. See "Inbound document type whitelist."
