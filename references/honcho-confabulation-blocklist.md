# Honcho Confabulation Blocklist

Single source of truth for the **known-false** facts that Honcho's dialectic
layer keeps re-deriving from stale dummy-data conversation history. The
"Honcho Drift Correction" cron reads this file: if any blocked term reappears
in the live peer card, it re-plants the negating conclusions and re-asserts
the clean card.

Verified by Andrew 2026-06-08. The curated peer card (honcho_profile) is the
authoritative layer; this list keeps the dialectic/observation layers in check.

## Blocked terms (must NOT appear as asserted facts about the user)

| Term / claim | Reality |
|---|---|
| Matte (alias) | FALSE — not an alias for Andrew |
| Sanja (spouse) | FALSE — test fixture, no spouse asserted |
| Ellie (child) | FALSE — HA test fixture |
| Jasper (child) | FALSE — HA test fixture |
| 3ds Max / 3D-pro | FALSE — not the user's software |
| RTX 5080 | FALSE — unverified hardware claim |
| Dearborn / Sterling Heights MI | FALSE — location not asserted |
| Swedish (language) | FALSE — language not asserted |
| Railway / Postgres (manifest) | FALSE — retired, not in use |
| Qdrant / Chroma | FALSE — proposed 2026-06-02, never installed (verified absent 2026-06-08) |
| Andrew "prefers Opus 4.8" (as a user preference) | FALSE — Andrew never asserted a personal model preference. NOTE: `claude-opus-4-8` IS a real, in-use model (see Known-TRUE) — flag only the *user-preference* claim, never the bare model name. |
| ThinQ | FALSE — not in use |
| "Backup VPS" / "backup server" (178.156.246.115) | MISLEADING — it's the **prod HA host** (ubuntu-2gb-ash-1), not a backup |
| VoiceChangerJarvis / voice-changer (active sister agent) | GROUNDED-BUT-STALE — was real, DECOMMISSIONED 2026-06-09 (archived to profiles/_decommissioned/voice-changer-20260609). Flag only the *active* claim; the bot genuinely existed, so this is a "no longer current" correction, not a confabulation. The ONLY active sister agent is HAJarvis. |

## Ground-truth corrections to re-assert when drift detected

- Andrew Alhaj. Occupation UNKNOWN — do not infer.
- HA entities Matte/Sanja/Ellie/Jasper are TEST FIXTURES, not real family.
- 178.156.246.115 = production Home Assistant host, NOT a backup.
- No spouse/children asserted.

## Known-TRUE — do NOT flag or add to blocklist

- **LanceDB IS installed and active** — `~/.hermes/knowledge_db/` (165 rows, `knowledge-store` skill, weekly dedup cron). It was proposed 2026-06-02 AND later installed (verified live 2026-06-08). Do not lump it with the false confabulations even though older notes said "never installed."
- `5.78.238.81` is the worker box (hil-1)'s own public IP, not a separate "primary host."
- **`claude-opus-4-8` is a REAL, in-use model** — configured on the `swarm-verifier` profile, and the Anthropic OAuth bypass auto-upgrades the main profile to Opus for complex reasoning. The bare model name is legitimate everywhere; only a claimed *personal preference* by Andrew is false. (Note: voice-changer also carried this model but was decommissioned 2026-06-09 — see blocklist.)
- **`deepseek-v4-flash`** (swarm-worker-a/b/c) and **`deepseek-v4-pro`** (executor, synthesizer, delegation) are real, configured models — never flag.

## Honcho topology (verified 2026-06-08 via SDK)

- **Workspace:** `hermes` (NOT `default` — an SDK client defaulting to `default` finds 0 peers).
- **Operator/user peer:** `8878729385` (Andrew's Telegram ID) — holds the real curated card (~22 facts / 26 conclusions). ALWAYS address the operator by this explicit peer ID, never the `peer="user"` alias.
- **AI peer:** `hermes` — holds the AI Identity Card (~22 facts).
- **Empty/decoy peers:** `root` (what `peer="user"` mis-resolves to in an isolated root-session — this caused the drift-cron false read), `ha-bot`, `-1003947663220` (cron channel) — all empty.
- **Discord peer:** `328062748585885696` (~10 facts).
- **Separate workspace** `hermes_swarm-verifier` exists with its own ephemeral `user-default-*` peers — unrelated to the operator card.
- **Lesson:** in any isolated/cron session, the `user` alias is unreliable — pin peer `8878729385` explicitly.

## How the cron uses this

1. Read live peer card via `honcho_profile(peer="8878729385")` — the explicit operator peer ID, NOT the `peer="user"` alias (see Honcho topology above; the alias mis-resolves to an empty `root` peer in isolated/cron sessions).
2. Scan for any blocked term above.
3. If found: `honcho_conclude` the matching reality statement(s) + re-assert
   the clean card via `honcho_profile(card=[...])`.
4. Stay SILENT when clean. Alert Cron channel only when a correction was made.
