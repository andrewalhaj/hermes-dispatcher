# Follow-up: skill_desc_reconcile.py + on_session_start heal hook never built

**Filed:** 2026-06-16  
**Context:** skill-cliff enforcement work (cron watchdog 38efb0814181)

## The gap

`hermes-maintenance/SKILL.md` (lines 450–454) documents a durable heal pattern as if it exists:

- `scripts/skill_desc_reconcile.py` — idempotent script that re-applies correct descriptions after every `hermes update` (which overwrites core skills)
- An `on_session_start` heal hook that runs it automatically on the next session after an update

**Neither exists on disk.** The audit tool (`skill_desc_audit.py`) exists. The doctrine exists. The reconciler and hook do not.

## Why it matters

The current watchdog (cron 38efb0814181) catches drift **every 6h**. But if `hermes update` overwrites a local skill with a bad description, the watchdog is the only catch — there's no automatic heal. The reconciler pattern would make the fix self-applying rather than requiring manual intervention after each update.

## What needs building

1. `skills/productivity/hermes-maintenance/scripts/skill_desc_reconcile.py`  
   — reads a "golden" descriptions manifest  
   — re-applies any that were overwritten by `hermes update`  
   — idempotent (safe to run multiple times)  
   — dry-run flag for preview

2. A manifest file (e.g. `references/skill-description-manifest.json`) of all canonical <=60-char descriptions — the "golden copy" the reconciler restores from

3. Wire it to `on_session_start` (or nearest equivalent) so it heals after every update automatically

## Note on scope

The doctrine warns explicitly: **do NOT conflate building the instrument with descriptions being fixed.** This is a nice-to-have automation. The watchdog already catches drift. Only worth building if `hermes update` starts regularly clobbering local skill descriptions.

## Pre-work before building

- Confirm `on_session_start` hook exists and fires reliably post-update  
- Check if `hermes update` actually touches `~/.hermes/skills/` (local profile) or only core builtins — if it doesn't touch local skills, the reconciler has no problem to solve
