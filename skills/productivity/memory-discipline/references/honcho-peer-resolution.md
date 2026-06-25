# Honcho peer resolution — pin the operator peer ID, not the `user` alias

Verified live via the Honcho SDK 2026-06-08. The `peer="user"` alias is UNRELIABLE
in isolated/cron sessions and silently reads the wrong (empty) peer. This caused a
drift-correction cron to report CLEAN on an empty read for multiple runs.

## Topology (workspace `hermes`)

- **Workspace is `hermes`, NOT `default`.** An SDK client that defaults to workspace
  `default` finds **0 peers** and looks broken. Always target workspace `hermes`.
- **Operator/user peer = the Telegram ID `8878729385`** — holds the real curated card
  (~22 facts / 26 conclusions). This is the peer to read/write for user-model work.
- **AI peer = `hermes`** — holds the AI Identity Card (~22 facts).
- **`root` peer = EMPTY** — in a fresh root-OS session the `peer="user"` alias resolves
  to a peer named `root`, which has no card. This is the trap: `honcho_profile(peer="user")`
  returns `None`/empty in a cron session but the real 22-fact card from an interactive
  `default`-profile session. Same call, different peer binding by session context.
- Other peers: `328062748585885696` (Discord, ~10 facts), `ha-bot`, `-1003947663220`
  (cron channel) — all empty or unrelated. A separate workspace `hermes_swarm-verifier`
  has ephemeral `user-default-*` peers, unrelated to the operator card.

## Rules

1. **In any isolated/cron/subagent session, pin the explicit peer ID `8878729385`** for
   `honcho_profile` / `honcho_conclude` — never the `peer="user"` alias.
2. **"Empty card" ≠ "clean card."** A watchdog that reads an empty peer must FAIL LOUD
   (alert), not conclude CLEAN. An empty/None read against a known non-empty baseline is a
   READ FAILURE. This is the same "empty ≠ healthy" trap as a blocked MEMORY.md.
3. **Cross-check the binding before trusting a read:** read the AI peer (`hermes`) too —
   if it's populated but the user peer is empty, the API/auth is healthy and the problem is
   peer resolution, not connectivity or data loss.
4. **Enumerate via SDK when topology is unknown:** `Honcho(api_key=..., workspace_id="hermes").peers()`
   then `h.peer(id).get_card()` per peer to find which one holds the facts. Source the key
   from `~/.hermes/.env` (`HONCHO_API_KEY`); the SDK won't pick it up implicitly.

## How to discover this yourself

The config has `honcho: {}` (empty) — workspace/peer are convention-based, not configured.
Don't assume `default`. Enumerate workspaces, then peers, then per-peer card fact-counts,
and find the peer whose count matches the interactive `honcho_profile(peer="user")` result.
That peer's ID is the operator peer to pin.
