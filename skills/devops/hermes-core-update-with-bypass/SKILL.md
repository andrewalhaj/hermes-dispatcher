---
name: hermes-core-update-with-bypass
description: "Hermes core update via hermes-claude-auth bypass."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [hermes, update, oauth-bypass, patches, cron, self-heal, maintenance]
    created_by: agent
load_when:
  - "user asks to run hermes update / update Hermes core on a bypass host"
  - "user asks about the OAuth bypass breaking after an update"
  - "complex tasks stopped upgrading to the heavy tier / classifier missing or always-on"
  - "ALL Anthropic models failing with 404 / Fable/Mythos shutdown / Fable 5 not available — even when requesting Sonnet or Opus"
  - "user asks to tune the complexity classifier, change the upgrade target model, or it upgrades too often/never"
  - "user asks about protecting patch files from being overwritten"
  - "user asks about the delegation-checkpoint guard or patch-guard cron"
---

# Hermes Core Update (with OAuth bypass + custom patches)

This host runs Anthropic via the **hermes-claude-auth OAuth bypass**, plus custom
patch files. `hermes update` rebuilds the venv and **breaks the bypass**, and the
bypass's own `install.sh` **clobbers customizations**. This skill is the proven,
gated sequence that survives both.

## 0. Approval gate (iron rule)
`hermes update` is a gated mutation. Present analysis + risks + rollback, get
explicit greenlight, snapshot first. Never run it inline reflexively.

## 0a. Pre-flight golden reconciliation — sync STALE goldens live→golden BEFORE the update (PROVEN 2026-06-20)

The self-heal restores live FROM golden. So a golden that has drifted STALE
relative to live is not a safety net — it's a loaded gun: post-update install.sh
clobbers live → patch_guard "heals" from the stale golden → silently reverts your
correct live code to an old version. **Before any update, diff every full-restore
golden against its live file and reconcile.**

```bash
P=/root/.hermes/patches; G=/root/.hermes/references/patch-guard
for f in anthropic_billing_bypass delegation_checkpoint skill_review_checkpoint \
         memory_checkpoint domain_ownership_checkpoint write_gate \
         kanban_checkpoint delegate_toolset_floor; do
  cmp -s "$P/$f.py" "$G/$f.golden.py" && echo "IN-SYNC  $f" || echo "DIFFERS  $f"
done   # use cmp -s (exit-code), NOT diff >/dev/null — the > trips the write-gate
```

For each DIFFERS, get the direction with `diff golden live` and decide which side
is correct. **Drift direction is NOT inferrable from mtime** — this session the
bypass golden was *newer* by 4 min yet *missing* a live block (a golden re-sync had
captured an older live state). Confirm direction by what the block DOES + whether
it's firing live (journal), then `cp live golden` (back up golden `.bak-<ts>` first,
verify byte-identical with `cmp -s`, syntax-check, confirm critical markers present).
After reconciling, run `patch_guard.py` once — SILENT + exit 0 proves all artifacts
now agree. Only then proceed to the update.

**The silent-death trap this caught: a bypass-CHAINED guard that is NOT in
sitecustomize AND NOT a patch_guard marker.** `kanban_phase_checkpoint` loads ONLY
via the `anthropic_billing_bypass.apply_patches()` chain (one of the 7 guards lives
in sitecustomize; this 8th does not), and patch_guard tracks ZERO markers for it.
It was firing live (journal showed hits) but its block was absent from the bypass
golden. Left unreconciled: install.sh ships vanilla bypass → patch_guard heals from
stale golden → the chained guard vanishes with nothing to alarm on. **Audit rule:
any guard chained from the bypass that is not independently golden-protected rides
entirely on the bypass golden being current — verify its block is IN the bypass
golden pre-update.** Grep the live bypass for every `import <guard>` / `.apply_patches()`
chain line and confirm each appears in `anthropic_billing_bypass.golden.py`.

## 0b. Pre-flight discovery sweep — find EVERY customization the update will clobber (PROVEN 2026-06-09)

The numbered pitfalls below cover the *known* customizations. But the lib tree
accumulates new core-file edits over time, and the update reverts **every**
git-tracked modification — including ones no golden protects. Before any update,
enumerate the full blast radius and map each modified file to its protection
status. This is how you catch the UNPROTECTED gap before it silently vanishes.

```bash
cd /usr/local/lib/hermes-agent
git status --short            # ' M' = modified tracked → update WILL revert it
git diff --name-only          # the precise list of at-risk core files
```
For EACH modified tracked file, ask: *does the self-heal restore it?* Cross-check
against `~/.hermes/scripts/patch_guard.py`:
- `_restore_full(...)` calls → whole-file golden restore (robust). e.g. the bypass.
- `_heal_honcho_format` / `_heal_bfull` → **anchor-based** surgical re-insert
  (fragile — see below). Covers `plugins/memory/honcho/__init__.py` and
  `gateway/run.py` (B-full).
- **No match anywhere → UNPROTECTED.** The update reverts it with nothing to
  restore it. This session that was `tools/delegate_tool.py` (a delegation
  api_key runtime-fallback patch + a stray debug-log block) — modified, no golden,
  zero patch_guard coverage. Would have silently reverted, plausibly re-breaking
  delegation post-rebuild.

Protection-status one-liner per file:
```bash
f=tools/delegate_tool.py
grep -c "$(basename $f)" /root/.hermes/scripts/patch_guard.py   # 0 = UNPROTECTED
ls /root/.hermes/references/patch-guard/*$(basename ${f%.py})* 2>/dev/null  # golden?
```
For any UNPROTECTED file: capture its diff to `/tmp` NOW as a safety net
(`git diff <f> > /tmp/<name>.patch`), then decide — (A) golden-protect it (add a
golden + a `_heal_*` to patch_guard), (B) re-apply by hand post-update, or (C)
confirm it's now redundant (the fix may be obsolete — e.g. a delegation api_key
e.g. a delegation api_key fallback becomes moot once PITFALL 7's `EnvironmentFile` loads the key properly
**Strip debug/credential-leaking cruft before immortalizing anything in a golden**
— delegate_tool's patch carried a `logging.warning("DELEGATION DEBUG ... api_key_head[:20]")`
that both spams the journal and leaks key prefixes; don't bake that into a golden.

Also sweep the venv (rebuilt by update AND install.sh):
```bash
SP=/usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages
grep -c "hermes-claude-auth managed\|delegation_checkpoint\|skill_review" $SP/sitecustomize.py
```
A venv rebuild also wipes the out-of-tree package set (lancedb/pylance/pandas/
pyarrow/sentence-transformers + playwright/faster-whisper/firecrawl-py).
`patch_guard.py` heals the knowledge-db set via `_heal_knowledge_db_packages`
(sentinel-import → `uv pip install --python <venv-py>`; the uv venv has NO pip
binary for installs). After an update, run `python3 ~/.hermes/scripts/patch_guard.py`
immediately rather than waiting for the 05:00 tick, then `knowledge.py status`.
`sitecustomize.py` is protected by `_heal_sitecustomize` (re-appends the blocks),
but verify the markers are present pre-update so you have a baseline.

**Venv rebuild also removes out-of-repo packages (PROVEN 2026-06-12):** the
knowledge store needs `lancedb`, `pylance`, `pandas`, `pyarrow`, `numpy`,
`sentence-transformers` — none are Hermes deps, all vanish on a venv rebuild and
`knowledge.py` dies on import (`No module named 'lancedb'`). The venv has NO pip;
reinstall post-update with:
`uv pip install --python /usr/local/lib/hermes-agent/venv/bin/python3 lancedb pylance pandas pyarrow sentence-transformers`
and verify `python3 ~/.hermes/scripts/knowledge.py status` returns a fact count.
Capture current pins pre-update: `venv/bin/python3 -m pip show <pkgs> | grep -E "^Name|^Version"`.

### Anchor-fragile patches on a large commit jump — B-full AND Honcho-format
### Anchor-fragile patches on a large commit jump — B-full AND Honcho-format

**De-risk the jump BEFORE launching: check every surgical anchor against
`origin/main` directly (PROVEN 2026-06-20, 311-commit jump).** Don't wait for the
post-update heal to discover an anchor moved — `git show` the target files on main
and grep for each anchor string. If all anchors survive, the heals will re-apply
automatically and the jump is far safer than its commit-count implies; if one is
missing, you know to re-port by hand BEFORE the update, not after a silent failure.
```bash
cd /usr/local/lib/hermes-agent
git fetch --quiet
git show origin/main:gateway/run.py | grep -c "logger = logging.getLogger(__name__)"   # B-full helpers anchor
git show origin/main:gateway/run.py | grep -c "if message_text is None:"                # B-full inject anchor
git show origin/main:gateway/run.py | grep -c "_bfull_retrieve"                          # 0 = our marker not yet upstream = patch still needed
git show origin/main:plugins/memory/honcho/__init__.py | grep -c 'rep = ctx.get("representation"'
git show origin/main:tools/delegate_tool.py | grep -c "effective_api_key = override_api_key or parent_api_key"
```
Also size the UNPROTECTED-file conflict risk the same way — decompose the delta into
OUR change vs MAIN's change: `git diff HEAD -- <f>` (ours) vs `git diff HEAD origin/main -- <f>`
(theirs). If main touched the SAME region as our patch, expect a stash-pop CONFLICT →
capture `git diff HEAD -- <f> > /tmp/<f>.patch` for hand re-apply. (This session
`kanban_tools.py` showed 45 ln ours / 101 ln theirs / 2 overlapping → flagged conflict;
`base.py` showed 4 ln ours / 0 theirs → clean.)

`_heal_bfull` and `_heal_honcho_format` are NOT whole-file restores; they
string-match an exact anchor in a ~20k-line upstream file and insert. On a large
jump (this session: **371 commits behind**) upstream may have refactored the
function around the anchor → the anchor misses → the heal **bails safely but the
patch stays DOWN** (B-full per-turn RAG injection silently stops; Honcho
drift-suppression silently off) until you manually re-port. The escape-hatch
message is `"... anchor not found — upstream likely refactored run.py; re-port
patch manually."` Treat BOTH as **expected possible manual-intervention steps**
on a big jump, not automatic. Post-update, verify by behaviour not by
"patch present": `grep -c "_bfull_retrieve(message_text)" gateway/run.py` AND a
live turn that proves memory is actually injecting. Do not declare the update
successful until a live turn confirms B-full fires (POLA: server-side present ≠
working RAG). After a successful (auto or manual) re-port, **re-sync ALL goldens
to the validated post-update state** so the next 05:00 self-heal protects the new
versions — otherwise it can revert correct post-update code back to a stale golden
the morning after (the both-files rule, applied to the whole golden set).

## Critical facts about THIS host
- **Agent class is `AIAgent`** (not `RunAgent`) in `run_agent.py`. Patches target `AIAgent`.
- **Bypass loads only on the Anthropic path** — `agent.anthropic_adapter` is imported
  lazily (`agent_init.py`, `api_mode == "anthropic_messages"`). DeepSeek-only sessions
  never trigger it. That's why provider-independent installs go in `sitecustomize.py`.
- **`sitecustomize.py`** lives in the venv site-packages and is the hermes-claude-auth
  import hook. Rebuilt by `hermes update` AND `install.sh`.
- **Patch files:** `~/.hermes/patches/anthropic_billing_bypass.py` (custom, ~958 lines,
  contains the complexity classifier `_classify_complexity`/`_maybe_upgrade_model`) and
  `~/.hermes/patches/delegation_checkpoint.py` (delegation guard).
- **Heavy-tier target is a decoupled constant `_HEAVY_MODEL`** (was `_OPUS_MODEL`;
  `claude-fable-5` as of 2026-06-10). Complex tasks upgrade Sonnet → `_HEAVY_MODEL`,
  NOT hardcoded to Opus — don't assume the destination, grep it.

> For TUNING the classifier (thresholds, signal list, changing the upgrade target)
> and the **system-prompt over-fire trap** that made it upgrade on *every* request,
> see `references/complexity-classifier-tuning.md`. Read it before touching
> `_classify_complexity` — the naive "scan everything" approach is a known footgun.

> For HOW to install custom runtime behavior into the agent loop (monkeypatch seams,
> `AIAgent` class, `_execute_tool_calls`, deferred MetaPathFinder, isolated-subprocess
> testing, idempotency), see `references/runtime-patching-pattern.md`.
>
> For WHO refreshes the OAuth token (no daemon — lazy, request-triggered, in
> `anthropic_adapter`), the reusable refresh functions, the single-use-refresh-token
> RACE, and the **single-writer pattern** for sharing the bypass token with another
> process (e.g. a hardened container), see `references/oauth-token-refresh-and-sharing.md`.

## PITFALL 1 — install.sh clobbers the classifier (PROVEN 2026-06-06; re-proven 2026-06-12 on fresh-host install)

> Scope note: this fires on ANY install.sh contact, including bootstrapping the
> bypass on a NEW host during migration — not just updates. Also: install.sh
> **hangs over non-interactive SSH** (final `systemctl --user restart` blocks
> without a user session bus). On remote hosts run its steps manually: copy the
> bypass to `~/.hermes/patches/`, append `sitecustomize_hook.py` to the venv
> sitecustomize if the marker is absent, then restore the classifier from golden.
> Full migration flow: `hermes-host-migration` skill.
`hermes-claude-auth/install.sh` ships a **vanilla** `anthropic_billing_bypass.py`
WITHOUT the complexity classifier (it was 833 lines vs our customized ~958). Running
install.sh silently overwrites the custom file → **complex tasks stop auto-upgrading
to the heavy tier (`_HEAVY_MODEL`), silently**. The bypass still *works* (auth OK) so the regression is invisible
without checking `grep -c _classify_complexity`.
**Fix:** always restore the customized file from a golden copy after any install.sh run.

## PITFALL 2 — `_HEAVY_MODEL` provider-disabled: ALL models return 404 (PROVEN 2026-06-12, Fable 5 shutdown)

> Diagnostic signal: every Anthropic model — `claude-sonnet-4-6`, `claude-opus-4-8`, etc. —
> returns **HTTP 404** with an error body naming the `_HEAVY_MODEL` (e.g., "Claude Fable 5
> is not available"), even when YOU didn't request that model. The gateway logs show
> `model=claude-sonnet-4-6` in the error line — that's the ORIGINAL requested model;
> the bypass's `_maybe_upgrade_model()` swapped it to `_HEAVY_MODEL` after the model
> name was logged but before the HTTP call. The classifier is always-on by design:
> if a task clears the signal threshold (which the keyword-saturated system prompt
> makes nearly certain — see `references/complexity-classifier-tuning.md`), every
> request upgrades to the disabled model. Auth is fine, the token is valid, the API
> endpoint is reachable — the model is just dead and everything routes to it.

**Quick test to confirm:** the error RESPONSE names Fable 5 but the request LOG says Sonnet.
Or check live: `grep _HEAVY_MODEL ~/.hermes/patches/anthropic_billing_bypass.py` → model shown.

**Fix (gated):** change `_HEAVY_MODEL` to an available model:
```bash
grep -n '_HEAVY_MODEL =' ~/.hermes/patches/anthropic_billing_bypass.py
# If it says claude-fable-5 and that's down, swap it:
#   _HEAVY_MODEL = "claude-opus-4-8"    (or "claude-sonnet-4-6" for no upgrade)
```
Then restart the gateway (gated — drops the live session). Verify by making an Anthropic
request: `grep 'provider=anthropic' ~/.hermes/logs/gateway.log | strings | tail -5`
should show 200s, not 404s.

**Prevention:** when Anthropic announces model deprecations/shutdowns, check whether the
bypass's `_HEAVY_MODEL` targets the affected model. The classifier has no health check —
it'll route to a dead model silently. Prefer targeting `claude-opus-4-8` (the stable
tier) over preview/limited models. Full incident details: `references/fable5-shutdown-incident.md`.

## PITFALL 3 — `config migrate --yes` flag removed in v0.16.0
Older runners used `hermes config migrate --yes`. v0.16.0 **removed `--yes`** →
`error: unrecognized arguments: --yes` and migration silently doesn't run.
Correct command is bare `hermes config migrate`. Verify with
`hermes config check | grep -i version` (want "Config version: N ✓").

## PITFALL 4 — satellite profiles don't auto-migrate
`hermes config migrate` only migrates the **default** profile. Satellites
(executor, ha-bot, voice-changer, stable-*) stay on the old version. Migrate each:
`hermes --profile <name> config migrate` (back up each config.yaml first).

## PITFALL 5 — the update severs your own session
The gateway restart in the update kills the controlling chat. Run the whole
sequence as a **detached system-level systemd-run unit** that reports each step
to Telegram out-of-band via the Bot API. Verify detachment works first:
`systemd-run --unit=test --collect /bin/bash -c '...'`.

## PITFALL 6 — system-level unit can't reach user systemd bus
A `systemd-run` unit (no user session bus) can't `systemctl --user restart`.
This is usually harmless: `hermes update` already cycles the gateways itself.
Don't treat the restart-step failure as fatal; verify gateway PIDs/start-times instead.

## PITFALL 7 — gateway units drop EnvironmentFile on EVERY update rebuild → silent env-key loss (PROVEN 2026-06-07, RE-PROVEN 2026-06-17)
**This fires after EVERY `hermes update`, not just fresh installs.** The update
regenerates `~/.config/systemd/user/hermes-gateway*.service` from template and
silently drops the `EnvironmentFile=-/root/.hermes/.env` line you added last time.
Both default AND ha-bot units lose it. POST-UPDATE this is a MANDATORY re-check,
not an occasional one — bake the `/proc/PID/environ` grep into the runner's
verification block so it never ships an env-less gateway again.

**2026-06-17 nuance — the failure can be MASKED, looking fine when it isn't.**
On this host delegation routes to a KEYLESS local endpoint
(`provider: custom:mac-studio`, `base_url: http://<studio>:11434/v1`). So even with
0 keys in the gateway env, `delegate_task` still works (ollama ignores the bearer).
A live delegation test returned `completed` — green — while the gateway env was
actually empty. Do NOT certify PITFALL 7 clear from a successful delegation; the
keyless-Studio path hides it. Verify the ACTUAL env load via `/proc/PID/environ`.
The keys still matter for every *other* `*_env` integration (BrowserBase, XAI,
Firecrawl, Telegram/Discord tokens) — those silently read empty.

The user-scoped gateway units (`~/.config/systemd/user/hermes-gateway*.service`)
may set only `Environment=` lines (PATH/VIRTUAL_ENV/HERMES_HOME) and **no
`EnvironmentFile=`**. Then `~/.hermes/.env` is NEVER loaded into the gateway
process env. Any feature resolving a key via `*_env` (e.g. delegation's
`api_key_env: DEEPSEEK_API_KEY`) sees an empty `os.environ`, falls through to a
stale cached value, and **401s silently** — subagents quietly stop spawning for
days with no alarm. The key on disk is fine; the env load is the bug.
**Diagnose:** `tr '\0' '\n' < /proc/$(systemctl --user show -p MainPID --value hermes-gateway.service)/environ | grep -cE '^(DEEPSEEK_API_KEY|ANTHROPIC|XAI)'` → 0 means nothing loaded.
**Fix (durable):** add `EnvironmentFile=-/root/.hermes/.env` (the `-` tolerates
absence/parse-skips) under `[Service]` in each gateway unit, `daemon-reload`,
restart. Verify `.env` is systemd-clean first (no `export ` prefix, no
`$`-expansion, well-formed `KEY=value`). Confirm post-restart: the same
`/proc/PID/environ` grep now shows the keys loaded.
**Immediate unblock (no restart of THIS session):** set the literal in
`config.yaml` `delegation.api_key` — it overrides the env path and the stale
cache. Restarting the **default** gateway bounces the current chat's backend
(do it last / let the user trigger); restarting **ha-bot** is safe from the
default session.
**Detection:** add a delegation health probe to the infra watchdog (resolve the
key the same way Hermes does — config literal first, then env — and
`GET https://api.deepseek.com/v1/models`; P1 on 401) so this never goes silent
again.

## PITFALL 7b — EnvironmentFile drop is SILENT when delegation points at a keyless custom provider (PROVEN 2026-06-17)

PITFALL 7 (above) describes the gateway unit losing `EnvironmentFile` on update.
The classic symptom is a delegation **401** (DeepSeek key unresolved). But when
`delegation.provider` is a **keyless local custom provider** (e.g.
`custom:mac-studio` → Ollama at `http://…:11434/v1`, `api_key: ""`), the failure
is INVISIBLE: delegation still *succeeds*, just silently on the local model,
because Ollama ignores the bearer token. There is no error to alarm on.

Diagnostic tells (don't trust "delegation worked" as proof the env is healthy):
- `/proc/$GW_PID/environ` key count is the ground truth:
  `tr '\0' '\n' < /proc/$(pgrep -f 'hermes_cli.main gateway run' | grep -v ha-bot | head -1)/environ | grep -cE '^(DEEPSEEK|ANTHROPIC|XAI|FIRECRAWL|TELEGRAM|DISCORD)'`
  `0` = EnvironmentFile not loaded, even if the gateway is "up" and delegating fine.
- A `delegate_task` that completes but reports `model: <local-model>` when you
  expected a cloud model is the behavioural signature.
- Don't over-diagnose: confirm what delegation is *configured* to use
  (`config.yaml` `delegation.provider/model`) before declaring a "fallback bug."
  A local-model delegation result may be CORRECT (keyless Studio is the intended
  target), not a degraded DeepSeek fallback. Read the config, then judge.

Fix is the same as PITFALL 7: add `EnvironmentFile=-/root/.hermes/.env` under
`[Service]` in BOTH `hermes-gateway.service` and `hermes-gateway-ha-bot.service`,
`daemon-reload`, restart. Back up each unit `.bak-<ts>` first. Verify post-restart
with the `/proc/PID/environ` grep above — expect the keys present on the NEW pid.

## PITFALL 8 — cron jobs crash `'dict' object has no attribute 'lower'` DURING the update window (PROVEN 2026-06-17)

Symptom: cron jobs (especially Memory Offload, Honcho Dedup, Daily Knowledge
Capture — anything on a `custom:<name>` provider) fail with:
```
File ".../agent/agent_runtime_helpers.py", line ~1284, in anthropic_prompt_cache_policy
    model_lower = eff_model.lower()
AttributeError: 'dict' object has no attribute 'lower'
```
`eff_model` (= `agent.model`) is a dict instead of the model-name string. This
happens transiently while the gateway is running a **half-updated state**: the
core code has been swapped but the gateway hasn't been cleanly restarted with the
*restored* bypass yet (PITFALL 1 window), so model resolution returns the custom
provider's model-config dict instead of the model string.

**Key insight: this is NOT a durable code bug — it SELF-HEALS after the gateway
restarts with the correct bypass + EnvironmentFile.** Before patching anything,
check whether jobs that have run SINCE the clean restart show `last_status: ok`:
```bash
python3 - <<'PY'
import json
d=json.load(open('/root/.hermes/cron/jobs.json'))
for j in d.get('jobs',[]):
    if 'custom' in str(j.get('provider','')):
        print(j['name'], j.get('last_status'), j.get('last_run_at'))
PY
```
If the hourly jobs (Memory Offload) already recovered post-restart, the remaining
`error` rows are just STALE STATUS from jobs that fire less often (02:30, 07:00)
and simply haven't re-run yet. Trigger one (`hermes cron run <job_id>`) to confirm
rather than rewriting cron prompts or core code. Resist the urge to "fix" a race
that already resolved — verify against the live post-restart state first.

Reproduce-to-rule-out: build the agent exactly as the scheduler does
(`resolve_runtime_provider(requested="custom:<name>")` → `AIAgent(model=job_model,
provider=runtime['provider'], …)`) in an isolated `python3 -` and confirm
`agent.model` is a string. A clean repro = the code path is fine = the failure was
the update-window race, not a standing bug.

## The proven sequence

### 1. Pre-flight (read-only)
```bash
hermes update --check                       # how many commits behind
hermes --version
cd /usr/local/lib/hermes-agent && git rev-parse --short HEAD
ls /root/hermes-claude-auth/install.sh      # bypass reinstall source present?
ls ~/.claude/.credentials.json              # OAuth creds present?
```

### 2. Snapshot
```bash
hermes profile create pre-update-YYYY-MM --clone-all
cp ~/.hermes/patches/anthropic_billing_bypass.py /tmp/bypass.ORIG.py   # GOLDEN
```
Keep that golden copy — it's the only way to undo PITFALL 1.

### 3. Detached runner
Write a script (see `references/update-runner.md` for the full template) that:
1. snapshots, 2. `hermes update --yes --backup` (fatal-abort on failure),
3. `hermes config migrate` (default) + `config check` per satellite,
4. re-run bypass `install.sh` with `HOME=/root` set,
5. restart gateways (best-effort), 6. live `AUTH TEST OK` health call,
7. report each step to Telegram. Read the bot token at runtime from `.env`
(never inline — the credential filter mangles it; use a script file).
Launch: `systemd-run --unit=hermes-update-$(date +%s) --collect bash <script>`.

### 4. Post-update verification (THE PART THAT MATTERS)
```bash
hermes --version                                    # new version live?
hermes config check | grep -i version               # default v? ✓
for p in executor ha-bot voice-changer stable-2026-06-02; do
  hermes --profile $p config check | grep -i version; done
# classifier survived install.sh?
grep -c _classify_complexity ~/.hermes/patches/anthropic_billing_bypass.py   # want 2
# live bypass + classifier dry-run
hermes chat -q 'Reply with exactly: AUTH OK' --provider anthropic -m claude-sonnet-4-6 -Q
```
If classifier count is 0 → PITFALL 1 hit → restore from golden:
```bash
cp /tmp/bypass.ORIG.py ~/.hermes/patches/anthropic_billing_bypass.py
```

### 4b. Reinstall knowledge DB packages (migration pitfall — mac mini)
`hermes update` rebuilds the venv and drops any packages not in the base requirements.
`lancedb`, `pylance`, `pandas`, `pyarrow`, `numpy`, `sentence-transformers`, and `torch`
are NOT in the base requirements but are required by `scripts/knowledge.py`. After any update:
```bash
uv pip install --python /usr/local/lib/hermes-agent/venv/bin/python3 \
  "lancedb==0.33.0" "pylance==7.0.0" "numpy==2.4.3" \
  "sentence-transformers==5.5.1" "pandas==3.0.3" "pyarrow==24.0.0"
# Verify
cd /root/.hermes && python3 scripts/knowledge.py status
```
Add this to the post-update runner script so it runs automatically.

### 4c. Two runner-script bugs that bit on 2026-06-17 (fix in the template)
- **`uv: command not found` inside the systemd-run unit.** The detached unit
  inherits a minimal PATH and `uv` lives in `~/.local/bin` (or the cargo path),
  not in it. Step 4b's `uv pip install` silently no-ops. FIX: hardcode the full
  path in the runner, e.g. `UV=$(command -v uv || echo /root/.local/bin/uv)` and
  call `"$UV" pip install ...`, OR `export PATH=/root/.local/bin:$PATH` at the top
  of the runner. The masking grace here is that a non-rebuilt venv keeps lancedb,
  so KB survives — but on a venv-rebuild update this would leave KB broken.
- **PITFALL-1 classifier check failed on a shell integer comparison.** A runner
  line like `if [ "$CLASSIFIER_POST" -lt 2 ]` blew up with
  `[: 0\n0: integer expression expected` because `grep -c` over a multi-file glob
  emits `0\n0` (one count per file), not a single integer. The restore-from-golden
  step then never fired → classifier stayed at 0 silently (PITFALL 1 unhealed).
  FIX: pin the grep to ONE file and coerce to int:
  `CLASSIFIER_POST=$(grep -c _classify_complexity ~/.hermes/patches/anthropic_billing_bypass.py | head -1)`
  Always verify the post-update count is exactly 2 with a single-file grep, and if
  <2, `cp /tmp/bypass.ORIG.py` back. On 2026-06-17 this had to be done by hand
  after the runner's silent miss.

### 5. Restart + confirm new code
```bash
systemctl --user restart hermes-gateway.service hermes-gateway-ha-bot.service
# confirm PIDs started AFTER the update; grep gateway logs for:
#   [anthropic_billing_bypass] Bypass installed
#   [delegation-checkpoint] installed
```

## Self-heal cron (protects all of the above)
Because install.sh / update overwrite the patch files, a daily watchdog restores
them from golden copies in `~/.hermes/references/patch-guard/`:
- Script: `~/.hermes/scripts/patch_guard.py` (no_agent cron, silent when healthy)
- Golden copies (6 protected artifacts as of 2026-06-09): `anthropic_billing_bypass.golden.py`,
  `delegation_checkpoint.golden.py`, `skill_review_checkpoint.golden.py`,
  `sitecustomize-block.golden.py`, `delegate-tool-fallback.golden.py` (the subagent
  api_key runtime-fallback snippet — anchor-based heal), plus `bfull-helpers.golden.py`
  / `bfull-injection.golden.py` for B-full, and the guard script itself.
- For the runtime-patching pattern (load seams, `_execute_tool_calls`, decoupled
  tunables, tags-aware matcher) see `references/runtime-patching-pattern.md`. A
  reusable calibration-test template for a guard lives at
  `scripts/test_skill_review_checkpoint.py` — adapt its fixtures per guard, require
  ALL GREEN before syncing golden / restarting.
- Checks MARKERS (not raw diff): `_classify_complexity` + `import delegation_checkpoint`
  in bypass; `def apply_patches` + `_deleg_checkpoint_patched` in guard; `delegation_checkpoint`
  in sitecustomize; `Fallback: when parent inheritance produces a falsy key` in
  `tools/delegate_tool.py` (`_heal_delegate_tool`, added 2026-06-09 — anchor
  `effective_api_key = override_api_key or parent_api_key`). On drift: backup → restore (bypass/guard) or re-append (sitecustomize)
  → syntax-check → report + restart command. **Does NOT auto-restart** (would surprise an
  active session); tells Andrew the command instead.

> **Golden byte-exactness gotcha (PROVEN 2026-06-09):** when creating a golden snippet
> for an anchor-based heal, the golden MUST be byte-identical to the live block or the
> heal re-inserts a subtly different version (and your revert→heal round-trip test fails
> to even detect the block). Do NOT author the golden with `write_file` — it strips
> trailing whitespace, so a live line ending in a stray space (e.g. `... parent was `)
> won't match. Either strip the cruft from the live file too (preferred — that trailing
> space was real cruft this session) then extract, OR copy the exact live bytes via
> Python slice (`src[anchor_end:next_marker]`) and write them verbatim. Always validate
> with a round-trip: simulate the update revert (`src.replace(anchor+golden, anchor)`),
> confirm the marker is gone, re-heal, and assert `healed == original` + compiles. A
> golden that doesn't round-trip-identical is a latent corruption waiting for the next heal.
- Cron: `0 5 * * *`, deliver `telegram:-1003947663220,discord:#cron-jobs`.
**After any intentional patch change, refresh the golden copies** or the watchdog reverts you.
**Both-files rule (PROVEN 2026-06-07):** any intentional edit to a guarded patch file
must be applied to BOTH the live file AND its `golden.py` in the same change, or the
05:00 self-heal silently reverts it next run. (Editing only `delegation_checkpoint.py`
to remove a noisy startup line would have come back at 05:00 — golden had to be edited
too.) The self-heal triggers on MARKERS, not raw diff, so non-marker edits (cosmetic
log-line removals, etc.) won't *trigger* a restore on their own — but a later genuine
drift restore would reintroduce the line from a stale golden. Edit both, every time.

## Rollback
```bash
hermes profile use pre-update-YYYY-MM
cp /tmp/bypass.ORIG.py ~/.hermes/patches/anthropic_billing_bypass.py
cd /root/hermes-claude-auth && HOME=/root ./install.sh
systemctl --user restart hermes-gateway.service hermes-gateway-ha-bot.service
```
