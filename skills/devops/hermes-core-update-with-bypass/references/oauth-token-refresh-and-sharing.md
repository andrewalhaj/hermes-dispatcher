# OAuth token: who refreshes it, and how to share it safely

Verified by reading `/usr/local/lib/hermes-agent/agent/anthropic_adapter.py`
(2026-06-07). This answers two questions that recur whenever the bypass token
is involved: **what keeps it alive**, and **how to let another process use it
without breaking refresh.**

## Who refreshes the bypass token (authoritative)

There is **NO standalone refresher daemon/cron/systemd-timer**. If you go
hunting for one you will find nothing — that's expected, not a bug. Refresh is
**lazy and request-triggered, owned by Hermes itself**:

- `resolve_anthropic_token()` → `_resolve_claude_code_token_from_credentials()`
  runs before every Anthropic request.
- It reads `~/.claude/.credentials.json` (`claudeAiOauth.{accessToken,
  refreshToken,expiresAt}`; `expiresAt` is **epoch ms**), checks validity with a
  **60-second expiry buffer** (`is_claude_code_token_valid`).
- If expired/near-expiry, `_refresh_oauth_token()` POSTs
  `grant_type=refresh_token` (client_id `9d1c250a-e61b-44d9-88ed-5944d1962f5e`)
  to `platform.claude.com/v1/oauth/token` (fallback `console.anthropic.com`).
- On success `_write_claude_code_credentials()` **atomically writes the new
  token back** to `~/.claude/.credentials.json` (temp file at 0600 +
  `os.replace`; preserves `scopes`, which Claude Code >=2.1.81 gates on —
  `user:inference` must be present).

Consequence: whichever Hermes process makes an Anthropic call owns refresh.
The token lives ~50 min; normal Hermes activity keeps it fresh.

## Reusable functions (don't reimplement refresh)

```python
import sys; sys.path.insert(0, "/usr/local/lib/hermes-agent")
from agent.anthropic_adapter import (
    refresh_anthropic_oauth_pure,        # (refresh_token, use_json=False) -> {access_token, refresh_token, expires_at_ms}
    _write_claude_code_credentials,      # (access_token, refresh_token, expires_at_ms) -> writes ~/.claude/.credentials.json
)
```
`refresh_anthropic_oauth_pure` is **pure** (doesn't touch local files);
`_write_claude_code_credentials` persists. Use both to refresh on demand.

## The dual-refresh RACE (the trap when sharing the token)

OAuth refresh tokens are commonly **single-use**: a successful refresh ROTATES
the refresh_token and invalidates the prior one. So if **two independent
refreshers** share one OAuth session (e.g. host Hermes + a container's own
`claude` CLI both reading a shared `~/.claude`), one refresh silently
invalidates the other's refresh_token → the loser is logged out → **silent auth
death mid-task**. This is the classic "fails at 3am" footgun.

## SINGLE-WRITER pattern (the safe way to share the token)

Make exactly one process the writer; everyone else reads.

1. **Host = sole refresher** (it already is — see above). Don't add a second.
2. **Sidecar copy, read-only to the consumer.** Mirror
   `~/.claude/.credentials.json` → a sidecar dir (chown to the consumer's uid,
   0600) and mount it **read-only** into the container at the CLI's expected
   `$HOME/.claude`. Read-only is the enforcement: the consumer **physically
   cannot rotate** the token (`Read-only file system` on write/delete), so the
   race is impossible — not merely discouraged. Verify with a write+delete
   attempt; both must fail.
3. **Keep-warm + mirror cron** (because read-only means the consumer can't
   refresh): a host `no_agent` cron, every 15 min, that:
   - refreshes the canonical token via the reusable functions above if within a
     ~20-min buffer (token life ~50 min → always fresh before any 5-30 min
     consumer task could outlive it),
   - atomically mirrors canonical → sidecar (temp+`os.replace`, chown, 0600),
   - **silent when healthy**, errors → Cron Jobs channel.
   Reference implementation lives at `~/.hermes/scripts/od_token_keepwarm.py`.
   This cron becomes **load-bearing** for long consumer tasks — alert on failure.

Trade-off to state plainly when proposing: the token now exists in a second
on-disk location (root-created, 0600, mounted RO). Flag the expanded footprint.
