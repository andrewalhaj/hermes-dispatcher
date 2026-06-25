# Patch-Guard Self-Heal: protecting managed files from silent clobbering

## The problem class

Some critical runtime patches live in files that routine ops OVERWRITE without warning:

| File | Clobbered by | Silent symptom |
|---|---|---|
| `~/.hermes/patches/anthropic_billing_bypass.py` | hermes-claude-auth `install.sh` (ships vanilla version) | complex tasks stop auto-upgrading Sonnet→Opus |
| venv `.../sitecustomize.py` | `hermes update` (venv rebuild) + install.sh | bypass hook + any chained startup patch gone |
| `~/.hermes/patches/<your-patch>.py` | patches-dir wipe | whatever the patch did stops |

The failures are SILENT — no error, no alarm. You discover them via a bill, an audit, or a
behavior that quietly stopped. Prompt-level reminders don't help; the file is just gone.

## The pattern: golden copies + a silent watchdog cron

1. **Stage golden copies** of every at-risk artifact under `~/.hermes/references/patch-guard/`:
   - full customized files (e.g. `anthropic_billing_bypass.golden.py`)
   - for files MANAGED by an installer (sitecustomize), stage only YOUR appended BLOCK as a
     `.golden.py` snippet — never overwrite the whole managed file; re-append the block instead.

2. **A `no_agent` watchdog cron** (`scripts/patch_guard.py`, daily) that:
   - checks each live file for required MARKERS (substrings), not a raw diff — markers survive
     harmless upstream churn while still catching a real clobber.
   - on drift: backs up the live file (`.bak-<ts>-driftheal`), restores from golden (full files)
     OR re-appends the block (managed files), validates Python syntax (`ast.parse`), and reports.
   - **silent when healthy** — prints nothing, so the no_agent cron delivers nothing (watchdog
     pattern). Reports to the Cron Jobs channel only on actual heal.

3. **Does NOT auto-restart the gateway.** A background gateway bounce mid-session is surprising
   and can interrupt active work (least-astonishment). The watchdog restores files + tells the
   user the exact restart command; restored patches load on the next gateway start. This one
   manual step is by design.

## Key implementation choices (learned this session)

- **Marker check, not byte-diff.** Use distinctive substrings (`_classify_complexity`,
  `import delegation_checkpoint`, `def apply_patches`, `_deleg_checkpoint_patched`). A byte-diff
  would false-positive on every benign upstream change.
- **Managed files get APPEND-heal, full files get RESTORE-heal.** For sitecustomize, first
  confirm the installer's own marker is present (`hermes-claude-auth managed`) before appending —
  if it's ALSO missing, the installer hasn't run yet; report that instead of appending into a
  broken file.
- **Always `ast.parse` the result.** A heal that produces invalid Python is worse than the drift.
- **Test all states before trusting it:** healthy→silent, each artifact clobbered→heals, then
  restore the live files. Run once via the cron path (`cronjob run`) to confirm `ok` + silent.

## Refresh the golden copies after any intentional change

The golden copies are the source of truth. Whenever you intentionally edit a protected patch
file (new classifier signal, new chained patch), re-copy it to `references/patch-guard/` —
otherwise the next self-heal will "restore" you back to the stale golden.

## This deployment (2026-06-06)

- Cron job `Patch Guard Self-Heal` (`23d4c20ae12d`), daily `0 5 * * *`, delivers to
  `telegram:-1003947663220,discord:#cron-jobs`.
- Golden copies: `anthropic_billing_bypass.golden.py` (945L, classifier + delegation chain),
  `delegation_checkpoint.golden.py`, `sitecustomize-block.golden.py`.
- Script: `~/.hermes/scripts/patch_guard.py`.
