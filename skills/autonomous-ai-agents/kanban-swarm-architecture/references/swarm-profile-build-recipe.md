# Swarm profile build recipe (verified live, Hermes v0.16.0, June 2026; re-verified 2026-06-18)

The exact sequence that stood up a 5-profile swarm pod end-to-end. Reproduce with
modifications. All `profile create` / `config set` / SOUL writes are GATED — present plan +
rollback, get greenlight, back up first.

## Roster built

| Profile | Clone from | Model | Role |
|---|---|---|---|
| swarm-worker-a/b/c | executor | deepseek-v4-flash | parallel workers (a=research, b=architecture, c=implementation) — distinct descriptions for decomposer routing |
| swarm-verifier | default | claude-sonnet-4-6 | skeptical review gate (stronger model on purpose) |
| swarm-synthesizer | executor | deepseek-v4-pro | assembler |

**Worker tier: deepseek-v4-flash, NOT -pro (corrected 2026-06-18).** Flash ran 41–59s/worker
vs 3–4min on -pro for parallel fan-out — far faster/cheaper, and worker chunks are bounded
investigation, not deep reasoning. Keep the synthesizer on -pro (it composes the whole
deliverable) and the verifier on Sonnet/Opus (the gate is where quality must concentrate).

3 distinct worker profiles (NOT one spawned 3×) → each gets its own `state.db` → **no SQLite
write-contention** under concurrency. At 30GB free the cost of 2 extra profiles is noise.
(If you ever DID run one worker profile N×, the open risk is N processes sharing one state.db
— "database is locked". Distinct profiles sidestep it by construction.)

## Step 1 — create (native tool, --description drives decomposer routing)

```bash
hermes profile create swarm-worker-a --clone-from executor --no-alias \
  --description "Parallel swarm worker — research & investigation. Executes one decomposed subtask in an isolated workspace, writes findings to the blackboard. Fast/cheap (DeepSeek). Does not verify or synthesize."
# ...worker-b (architecture & design), worker-c (implementation & detail) — same shape
hermes profile create swarm-verifier --clone-from default --no-alias \
  --description "Skeptical verification gate. Reviews combined worker output; blocks with comments if incomplete/wrong; only passes clean work. Does NOT do the work or synthesize."
hermes profile create swarm-synthesizer --clone-from executor --no-alias \
  --description "Synthesizer. Wakes only after the verifier passes. Assembles approved output into the final deliverable. Composes; does not re-research."
```
Verify: `hermes profile list | grep swarm-` → check models.

## Step 1b — ⚠️ FIX THE INHERITED PROVIDER, not just the model (burned 2026-06-18)

**`--clone-from <src>` copies the SOURCE profile's ENTIRE `model:` block — `provider`,
`base_url`, `api_mode`, `api_key_env` — not just the model name.** `executor` points at the
Mac Studio (`provider: custom:mac-studio`, `base_url: http://100.93.2.43:11434/v1`). So every
DeepSeek worker cloned from it inherits the STUDIO provider, and setting only `model.default`
leaves it pointed at the wrong endpoint — `model=deepseek-v4-flash` but `provider=custom:mac-studio`,
which 404s (DeepSeek model name on the Ollama endpoint) or silently mis-routes. Set the FULL
quartet on every DeepSeek clone, not just the model:

```bash
for p in swarm-worker-a swarm-worker-b swarm-worker-c swarm-synthesizer; do
  hermes --profile "$p" config set model.default deepseek-v4-flash   # -pro for synthesizer
  hermes --profile "$p" config set model.provider deepseek
  hermes --profile "$p" config set model.base_url "https://api.deepseek.com/v1"
  hermes --profile "$p" config set model.api_mode chat_completions
  hermes --profile "$p" config set model.api_key_env DEEPSEEK_API_KEY
done
```
Also set each worker's `delegation.model` to its tier (a worker that itself calls
`delegate_task` otherwise inherits whatever the clone source had). **Verify provider AND
base_url after, not just the model string** — the model name looking right is the trap that
hides the wrong provider. The verifier (cloned from `default`) correctly keeps
`provider: anthropic` — do not touch it.

## Step 2 — scrub the inherited plaintext key (DeepSeek clones only)

`config.yaml` cannot be edited by `patch`/`write_file` (security write-guard refuses). Use
the CLI, `--profile` scoped:
```bash
for p in swarm-worker-a swarm-worker-b swarm-worker-c swarm-synthesizer; do
  hermes --profile "$p" config set model.api_key ""
done
```
Safe because `api_key_env: DEEPSEEK_API_KEY` + each `.env` has the key → env fallback covers
auth. **Do NOT touch swarm-verifier** — its `default`-inherited Anthropic/OAuth auth is the
real working auth, not a vestigial key.

## Step 3 — role SOULs + autonomy AGENTS.md (gated write_file, .bak first)

Workers can keep the lean inherited `executor` SOUL, but a swarm-specific SOUL is better
(blackboard contract + anti-fabrication + "no clarifying questions, you're headless"). Rewrite
the two that genuinely need a distinct posture, and give every worker/synthesizer a shared
autonomy-compatible `AGENTS.md`:
- **swarm-verifier/SOUL.md** — adversarial gate: read all worker output, check claims are
  supported, `kanban_block` with *specific actionable* comments naming the exact defect
  ("Worker B's failover plan has no split-brain handling for EU"), never vague ("needs more
  detail"); does NOT do the work or synthesize; "looks fine" is not verification.
- **swarm-synthesizer/SOUL.md** — assembler: read verifier-approved output, compose into one
  coherent deliverable, resolve overlaps, do NOT re-research or re-verify or invent new claims.
- **Shared worker/synth AGENTS.md** — the main agent's *discipline* (skills-scan,
  verify-before-done, anti-fabrication, absolute-path introspection per the introspection
  doctrine) MINUS the interactive mechanics a headless leaf can't use: no WRITE-GATE, no
  recall-gate, no approval-wait, no compaction checkpoint. Add explicitly: "you run headless,
  do not present plans and wait for greenlight, do not ask clarifying questions — interpret,
  state your assumption in one line, execute; if genuinely dangerous/out-of-scope, kanban_block."
  Give the verifier a DISTINCT AGENTS.md (it gates, doesn't execute — keep the absolute-path
  rules, drop the "no write gate" line). Profile AGENTS.md auto-injects by default.

## Step 4 — verify the whole build

```bash
hermes kanban assignees | grep swarm-                # all 5 on disk, assignable
# model + PROVIDER + base_url per profile (provider is the gotcha — check it, not just model):
for p in swarm-worker-a swarm-worker-b swarm-worker-c swarm-verifier swarm-synthesizer; do
  python3 -c "import yaml;m=yaml.safe_load(open('/root/.hermes/profiles/$p/config.yaml'))['model'];print('$p',m.get('default'),m.get('provider'),m.get('base_url',''))"
done
# keys scrubbed on 4 deepseek profiles, env fallback present:
for p in swarm-worker-a swarm-worker-b swarm-worker-c swarm-synthesizer; do
  grep -c DEEPSEEK_API_KEY ~/.hermes/profiles/$p/.env        # 1
done
```

## Rollback

`hermes profile delete swarm-worker-a swarm-worker-b swarm-worker-c swarm-verifier swarm-synthesizer`
— clean, zero impact on existing profiles. SOUL edits have `.bak-<ts>`.

## The manual-dispatch config that pairs with this (also via `hermes config set`)

```bash
hermes config set delegation.max_concurrent_children 8   # 8 only if multi-swarm/fleet confirmed; else 6
hermes config set kanban.dispatch_in_gateway false       # MASTER SWITCH: kills autonomous tick
hermes config set kanban.auto_decompose false            # no auto fan-out
hermes config set kanban.auto_decompose_per_tick 8       # inert while dispatch off; ready if re-enabled
```
With `dispatch_in_gateway: false`, nothing spawns until a human runs `hermes kanban dispatch`
— this is the cost governor AND cron isolation. The `patch` tool will refuse config.yaml; this
CLI path is the sanctioned one and writes are visible/verifiable via read-back. (Andrew's stack
runs bounded-autonomy ON — `dispatch_in_gateway: true` — so leave the tick alone unless he asks.)
