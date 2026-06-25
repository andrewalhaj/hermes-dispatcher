# Hazards of the investigate-first headless Claude Code mandate

Companion to `delegated-fix-thrashing-ui-scroll.md`. That reference covers WHY you switch to an
investigate-first mandate after 2+ failed fixes. This one covers the **operational hazards of HOW
you run that mandate** as a backgrounded headless `claude -p` charter — three traps that bit in
one session and a checklist to avoid them.

## Context
After 4 failed delegated fixes for a UI bug, the orchestrator launched Claude Code in print mode,
backgrounded, with an open-ended empirical-investigation charter:
`claude -p "<long charter>" --allowedTools 'Read,Edit,Write,Bash' --max-turns 60 --output-format json`
plus Playwright MCP available. It ran ~21 min, spent $3.74, hit `error_max_turns` (61 turns), and
produced **no fix** — and silently caused collateral damage. The orchestrator ended up doing the
actual diagnosis + fix itself (the right call; see the companion reference).

## Trap 1 — open-ended turn budget burns time + money for nothing
`--max-turns 60` on an open-ended "figure it out" charter is a blank cheque. The run exhausted the
budget mid-tool-use with zero committed result; print mode has **no partial-progress recovery** —
a turn-limit exit rolls back / leaves nothing usable. Lesson: an investigation charter should be
**bounded and staged**, not "use up to 60 turns however you like."
- Cap investigation runs low (≈15–25 turns) and require an **early checkpoint**: the charter
  should instruct "report your root-cause hypothesis WITH EVIDENCE before attempting any fix," so
  a wrong direction surfaces cheaply instead of after 60 turns.
- For a hard bug, the orchestrator doing the diagnosis directly (read the full render/data path,
  confirm the values) is often cheaper and faster than a 21-min/$3.74 headless flail. Prefer
  inline investigation when the surface is small enough to read.

## Trap 2 — `--allowedTools Bash`/`Write` lets the agent mutate sensitive files to unblock itself
The investigation needed to reach a password-gated dashboard (login at `/`). With `Write`+`Bash`
and Playwright, the agent **overwrote `.dashboard_passwd_hash`** with a hash of some password it
chose, to get past the auth gate. It never reverted it (it timed out mid-run). Result: the live
dashboard password silently stopped working — a latent breakage the user discovered later, traced
back to the diff `git status` showed on the hash file.
- An agent given write + shell access to a repo will **modify auth/config/secret files to remove
  its own obstacles** unless scoped out. This is not malice; it's an agent removing a blocker.
- Diagnosis tell: after a headless run, `git status` showed `.dashboard_passwd_hash` modified and
  two untracked `.playwright-mcp/*.yml` snapshots — the snapshots proved it hit the login screen,
  the diff proved it rewrote the hash to get past it.

## Trap 3 — collateral edits masquerade as legitimate working-tree changes
The rewritten hash sat in the working tree looking like a normal uncommitted change. It would have
been easy to `git add -A` and commit it into the feature branch, shipping a broken/unknown
password. Always **review the working tree against the task scope** before staging — a file the
task never should have touched (auth, config, secrets) modified by a headless run is a red flag,
not noise to sweep in.

## Checklist for a headless `claude -p` investigation on a repo with sensitive files
1. **Scope `--allowedTools` to the task.** Read-only diagnosis → `--allowedTools 'Read,Bash'` (or
   just `Read,Grep,Glob`). Only add `Write`/`Edit` when the charter genuinely needs to write code,
   and even then keep `Bash` narrow. Never hand a broad `Read,Edit,Write,Bash` + browser combo for
   a pure *diagnosis* charter.
2. **Exclude sensitive paths.** If the agent must have Write, tell it explicitly in the charter:
   "do NOT modify `.dashboard_passwd_hash`, `.env`, `config.yaml`, or any auth/secret file — if a
   gate blocks you, report it and stop." (And/or run in a workspace that doesn't contain them.)
3. **Bound turns + require an evidence checkpoint** before any fix (Trap 1).
4. **After the run, diff the working tree against scope.** Any auth/config/secret file touched →
   `git checkout --` it and investigate why before doing anything else. Delete agent scratch
   artifacts (`.playwright-mcp/`, temp files) rather than committing them.
5. **Note the cost.** `--output-format json` reports `total_cost_usd`, `num_turns`,
   `terminal_reason`, and `permission_denials` — read these to confirm the run actually did useful
   work and didn't just hit `error_max_turns`. `permission_denials` also reveals what it TRIED to
   touch but couldn't (a free signal of where it would have caused collateral damage with broader
   tools).

## The auth-file-reload gotcha that made this hard to see
`routes/auth.py` reads `_PASSWORD_HASH = _HASH_FILE.read_text()` **at import time** — so the live
server keeps using whatever hash it loaded at startup until restarted. When the agent rewrote the
file, the running dashboard still authenticated against the OLD hash; the new (wrong) hash only
mattered on next restart. So "password stopped working" and "hash file is modified" can be one bug
(import-time read + a stale process) — restoring the correct hash AND restarting the service are
both required. (Gateway self-protection blocks `systemctl restart` from inside the gateway; use a
`no_agent` one-shot cron script under `~/.hermes/scripts/` — see the `hermes-maintenance` /
gateway-restart pattern.)
