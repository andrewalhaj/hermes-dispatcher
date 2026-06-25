# Hermes Core Update Plan — 2026-06-20

**Status:** PREPARED + RE-VERIFIED 2026-06-20 PM, awaiting greenlight. Nothing mutated yet.
**Current:** v0.16.0 (2026.6.5), local `770448c5b` (+1 carried commit), upstream `c253b073`.
**Target:** origin/main = **version "0.17.0"** — **311 commits behind**. ("0.17.0" is what main's pyproject declares; the moving CalVer tag is v2026.6.19.)

## ⟡ RE-VERIFICATION RESULTS (2026-06-20 PM) — readiness GREEN, 2 pre-flight fixes required

### Self-heal: the 4 surgical anchors ALL survive on origin/main (top risk CLEARED)
The plan's #1 fear was anchor-miss on the 311-jump. Verified against `git show origin/main:<file>`:
- B-full `gateway/run.py`: helpers anchor `logger = logging.getLogger(__name__)` ✓, inject anchor `if message_text is None:` ✓ (our `_bfull_retrieve` marker NOT yet upstream ✓ = patch still needed + will re-apply)
- Honcho `__init__.py`: target block `rep = ctx.get("representation"` ✓
- delegate_tool.py: anchor `effective_api_key = override_api_key or parent_api_key` ✓
→ All three surgical heals should re-apply automatically post-update. Still verify by LIVE behaviour, not "marker present."

### 2 STALE GOLDENS — live is correct, golden must be synced ← live BEFORE post-update install.sh
- **`anthropic_billing_bypass.golden.py`**: live has a 13-line `kanban_phase_checkpoint` chain block (lines 1004–1016) that golden LACKS. `kanban_phase_checkpoint` loads ONLY via this bypass chain (NOT in sitecustomize, NOT a patch_guard marker) yet is FIRING LIVE (journal 01:30/02:00 today). If golden stays stale → post-update install.sh clobbers live bypass → patch_guard heals from stale golden → kanban_phase_checkpoint SILENTLY DIES, nothing alarms. **MUST sync golden ← live pre-update.**
- **`memory_checkpoint.golden.py`**: golden is 2026-06-09; live (2026-06-18) has the per-profile `_active_hermes_home()`/`_active_paths()` HERMES_HOME fix + the `_STARTUP_CHECKED` session-start check. Not update-triggered (markers present, no install.sh contact), but a latent revert risk on any future drift-heal. **Sync golden ← live now while we're here.**
- Other 6 full-restore goldens: IN SYNC ✓ (delegation_checkpoint, skill_review_checkpoint, domain_ownership_checkpoint, write_gate, kanban_checkpoint, delegate_toolset_floor).

### Blast radius re-measured — 5 core files
| File | Our local Δ | Main's Δ since base | Conflict? |
|---|---|---|---|
| `gateway/platforms/base.py` | 4 ln (.html/.7z) | **0 ln** | CLEAN — stash-pop applies, but UNPROTECTED → capture /tmp net |
| `tools/kanban_tools.py` | 45 ln (skill-pin) | **101 ln, 2 overlap our region** | **CONFLICT LIKELY** — hand re-apply from /tmp net |
| `gateway/run.py` | 93 ln | (anchor heal) | auto-heal ✓ |
| `plugins/memory/honcho/__init__.py` | 26 ln | (anchor heal) | auto-heal ✓ |
| `tools/delegate_tool.py` | 26 ln | (anchor heal) | auto-heal ✓ |

### Carried Telegram commit 770448c5b — REDUNDANT on main, safe to drop
main carries equivalent+superset telegram reconnect fixes: `d6137453a drain stale httpx polling conns on reconnect`, `2470434d6 probe polling liveness after reconnect`, `476c89743 gate send() on send-path health after reconnect storms`. → On pull conflict, DROP ours; verify replay behaviour post-update.

### Total modified tracked: 84 files = 5 core (above) + ~79 skill .md (cosmetic frontmatter, low risk).

### Two gated writes need greenlight:
1. **Pre-flight:** sync 2 stale goldens ← live (write to patches/patch-guard/ → gated). Back up each golden `.bak-<ts>` first.
2. **The update itself** (`hermes update`) → gated; detached systemd-run runner per PITFALL 5.

## Pre-flight facts (verified read-only)
- Anthropic bypass WORKS now: live `PREUPDATE AUTH OK` via claude-sonnet-4-6.
- Classifier healthy: `_classify_complexity` count = 2 (live AND golden).
- `_HEAVY_MODEL = "claude-opus-4-8"` (live AND golden) — NOT the dead Fable 5. Safe.
- KB deps healthy in **venv** python: numpy 2.4.3, lancedb, sentence-transformers, pandas, pyarrow. (Host py3.12 lacks them — irrelevant; knowledge.py runs on venv py3.11.)
- `.env` present, mode 600, 24KB. Key-name mangling in console output = Hermes credential filter, NOT a file problem.
- **KEY HOST CORRECTION:** this host loads `.env` IN-PROCESS via `load_dotenv` (`gateway/run.py` + `hermes_cli/env_loader.py`), NOT systemd `EnvironmentFile`. Neither gateway unit has an `EnvironmentFile=` line and `/proc/PID/environ` shows 0 keys — **this is EXPECTED and HEALTHY here.** PITFALL 7's `/proc` grep is a FALSE-POSITIVE signal on this host. Verify env health FUNCTIONALLY (live key-using integration), not via `/proc`.
- Update mechanism: auto-stash uncommitted → pull → auto-restore stash on top (`non_interactive_local_changes: stash`). `pre_update_backup: true`, `backup_keep: 5`. No `reset --hard`, no `git clean` → ignored paths (venv/node_modules) untouched.

## Blast radius — local changes the stash/restore must preserve
### Modified tracked CORE code (5 files):
| File | Diff | Protection | Action |
|---|---|---|---|
| `gateway/run.py` | 93 ln | `_heal_bfull` (ANCHOR) | Self-heal; **anchor may miss on 311-jump** → verify B-full fires by live behaviour |
| `plugins/memory/honcho/__init__.py` | 26 ln | `_heal_honcho_format` (ANCHOR) | Self-heal; same anchor risk |
| `tools/delegate_tool.py` | 26 ln | `_heal_delegate_tool` (ANCHOR) | Self-heal |
| `gateway/platforms/base.py` | 13 ln | **UNPROTECTED** | Adds `.html`+`.7z` doc types. Capture diff to /tmp; re-apply by hand if stash-restore conflicts |
| `tools/kanban_tools.py` | 54 ln | **UNPROTECTED** | Skill-pin existence validation guard. Capture diff to /tmp; re-apply by hand if lost |

### Carried commit (committed, NOT stashed):
- `770448c5b fix(telegram): drop pending updates on reconnect to prevent replay`
- Local main is **divergent** (1 ahead / 311 behind). Upstream now has equivalent fixes (`2c174bce2`, `5191c1c2c`). Pull will merge/rebase → our commit may conflict OR be redundant. **Decision needed:** likely safe to drop post-update if upstream covers replay-on-reconnect; verify Telegram replay behaviour after.

### ~80 modified SKILL.md files:
- All `*.bak-...-reconcile` description-shortening edits from 2026-06-12. Cosmetic frontmatter. Low risk — stash-restore handles them; conflicts here are harmless (skills, not core).

### Patch files (NOT git-tracked, in ~/.hermes/patches/ — git ops don't touch them):
- `anthropic_billing_bypass.py` — clobbered only by install.sh (PITFALL 1). Golden verified in sync.
- `delegation_checkpoint.py`, `skill_review_checkpoint.py`, etc. — golden-protected.

## Pitfalls that WILL fire (and the response)
1. **PITFALL 1** install.sh ships vanilla bypass w/o classifier → restore `cp /tmp/bypass.ORIG.py …` (golden verified, markers=2).
2. **PITFALL 5** gateway restart severs THIS chat → run update as DETACHED unit reporting to Telegram. NOTE: `systemctl --user` bus unreachable from this session ("No medium found") → use SYSTEM-level `systemd-run` (root); update cycles gateways itself (PITFALL 6).
3. **PITFALL 8** cron `'dict' object has no attribute 'lower'` during half-updated window → SELF-HEALS after clean restart. Don't patch; verify post-restart cron `last_status: ok`.
4. **venv rebuild** may drop KB packages → reinstall pinned: `uv pip install --python /usr/local/lib/hermes-agent/venv/bin/python3 "lancedb==0.33.0" "pylance==7.0.0" "numpy==2.4.3" "sentence-transformers==5.5.1" "pandas==3.0.3" "pyarrow==24.0.0"`. (uv full path — minimal PATH in detached unit.)
5. **Anchor-fragile heals on 311-jump** (B-full, honcho) may bail safely but leave patch DOWN → re-port by hand; verify by LIVE behaviour not "patch present".

## Proven sequence (gated — executes only on greenlight)
1. **Safety net (pre):** `cp ~/.hermes/patches/anthropic_billing_bypass.py /tmp/bypass.ORIG.py`; capture unprotected diffs: `git diff gateway/platforms/base.py > /tmp/base.py.patch`, `git diff tools/kanban_tools.py > /tmp/kanban_tools.py.patch`; `hermes profile create pre-update-2026-06-20 --clone-all`.
2. **Update:** `hermes update --yes --backup` (detached system systemd-run, Telegram-reporting).
3. **Migrate:** `hermes config migrate` (default) + per-satellite `hermes --profile <p> config migrate` (executor, ha-bot, voice-changer, stable-*). Back up each config.yaml first.
4. **Restore patches:** re-run bypass install.sh w/ `HOME=/root`; restore classifier from /tmp golden if count<2 (single-file grep, coerce int).
5. **KB deps:** reinstall pinned set (step 4 above).
6. **Verify (THE PART THAT MATTERS):** `hermes --version`; classifier count==2; live `AUTH OK` Anthropic call; B-full fires by live turn; delegation completes; cron `last_status` post-restart; unprotected files present (re-apply from /tmp if not).
7. **Restart + confirm:** gateways restart, PIDs post-update, logs show `Bypass installed` + `delegation-checkpoint installed`.
8. **Re-sync goldens** to validated post-update state (both-files rule).

## Rollback
```
hermes profile use pre-update-2026-06-20
cp /tmp/bypass.ORIG.py ~/.hermes/patches/anthropic_billing_bypass.py
cd /root/hermes-claude-auth && HOME=/root ./install.sh
systemctl --user restart hermes-gateway.service hermes-gateway-ha-bot.service
```
Plus: `git stash list` → restore stash if update left local edits stashed; re-apply /tmp/*.patch for unprotected files.

## Open questions for Andrew
1. **Carried Telegram commit** `770448c5b` — keep (risk merge conflict) or drop (upstream `2c174bce2`/`5191c1c2c` look equivalent)? I lean: attempt pull, drop if redundant + verify replay behaviour.
2. **Timing** — 311-commit jump is heavy. Off-peak (2–5 AM UTC) advised to avoid Anthropic overload during post-update verification turns.
3. **Backup** — `pre_update_backup: true` already zips HERMES_HOME. Proceed with that + profile clone, or skip the zip (`--no-backup`) since profile-clone covers it?
