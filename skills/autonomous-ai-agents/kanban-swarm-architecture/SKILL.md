---
name: kanban-swarm-architecture
description: "Kanban swarm architecture: operator adoption decisions."
version: 1.2.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, multi-agent, swarm, architecture, delegation, planning]
    related_skills: [kanban-orchestrator, kanban-worker, kanban-codex-lane]
load_when:
  - "user asks whether to adopt Kanban, build a swarm, or turn profiles into a team"
  - "user asks how to size a worker fleet, how many concurrent workers a host can run"
  - "user asks about full swarm capabilities or hermes kanban swarm"
  - "deciding between delegate_task, cron, and Kanban for a class of work"
  - "evaluating a third-party kanban / multi-agent orchestration tool"
  - "user wants 'I talk to you only, you delegate to the right profiles'"
---

# Kanban / Swarm Architecture (operator-side)

This is the **planning layer**: deciding whether and how to stand up a multi-agent
Kanban setup. It is NOT the in-worker routing playbook (`kanban-orchestrator`) or the
worker lifecycle (`kanban-worker`) — those are auto-injected into spawned workers. Load
this when the user is *architecting the team*, not executing a routing task.

## Kanban is a NATIVE Hermes feature — not a third-party add-on

`hermes kanban` ships in-box (verified v0.16.0): a durable SQLite board at
`~/.hermes/kanban.db`, shared across profiles, dispatched by a loop **inside the running
gateway** (default tick `kanban.dispatch_interval_seconds: 60`). When someone pitches "a
kanban thing" from a blog/Reddit post, the decision is NOT "install their thing" — it's
"adopt the always-on autonomous model they're selling, or a model that fits this host."
Docs: `https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban`.

## Choosing the primitive: delegate_task vs cron vs Kanban

| Need | Tool |
|---|---|
| Short reasoning answer the parent needs *before continuing*, no human, result into parent context | `delegate_task` (RPC, fork→join, ephemeral — dies if the parent turn is interrupted) |
| Time-triggered idempotent job (backup, audit, brief) | cron (`no_agent` or LLM-driven) |
| Work that must **survive restarts / context compaction**, cross agent boundaries, allow human interjection, or be discoverable after the fact | Kanban (durable queue + state machine) |

One-liner: `delegate_task` is a function call; Kanban is a work queue where every handoff
is a row any profile or human can read/edit. They coexist — a Kanban worker may call
`delegate_task` internally. **Do NOT route one-shot asks through a 5-process board** — that
is added surface for no gain. Reserve Kanban for genuinely parallel, long-running,
multi-track jobs.

## The swarm command (verified shape)

```
hermes kanban swarm "<goal>" \
  --worker PROFILE:TITLE[:SKILL,SKILL] \   # repeatable — N parallel workers
  --verifier PROFILE \                     # wakes only after all workers finish
  --synthesizer PROFILE \                  # wakes only after verifier signs off
  [--idempotency-key K] [--priority N] [--tenant T]
```
There is **NO `--dry-run` on `swarm`** (only on `dispatch`). To validate a graph without
spawning: `swarm --json` to inspect, or build cards then `dispatch --dry-run`.

## Sizing the fleet to host RAM (the hard constraint)

Workers are **full OS processes (~400–500MB each)**, not threads. CPU is rarely the wall
(agents are I/O-bound on LLM calls); **resident RAM is**. Compute the ceiling from real
headroom, not core count:

- Baseline = running gateways (each ~350–450MB) + OS + Docker containers already resident.
- A full swarm of 4 workers + verifier + synthesizer = 6 processes ≈ **2.4–3GB transient**.
- On an 8GB box that means swapping → OOM risk under Docker + other load. Safe ceiling there
  is **2–3 concurrent workers**, matching `delegation.max_concurrent_children: 3`.
- 16GB comfortably runs 2–3 workers; 32GB runs a full swarm + Docker with margin.

Always probe live before promising swarm capacity: `free -h` (truly-free vs cache),
`ps -eo pid,rss,comm --sort=-rss | head`, `docker stats --no-stream`. See
`references/host-sizing-for-workers.md`.

## New project → board, NOT a new agent (the default, Andrew 2026-06-09)

When the user asks *"should I create a new agent/profile for project X?"* the default answer is **NO — start it as a board under the existing orchestrator, not a new profile.** A profile is a persistent specialist with real standing cost; a project is usually just a workstream. Don't stand up an identity you'll have to feed and audit unless the project genuinely demands one.

**A new profile costs:** its own MEMORY.md/USER.md hot tier (another orphan-coverage surface), its own skills/cron/.env, **its own always-on gateway process + Telegram bot (another chat window — the opposite of single-voice)**, its own session+state DB. Every profile is parallel state to keep clean and in sync.

**A new project gets these CHEAPER primitives instead — no new identity:**
- **A board per project** (`hermes kanban boards`, `--board <slug>`) — the native project container.
- **Isolated per-task workspaces** — `scratch` / `worktree` / `dir:<path>` give code work a sandbox without a profile.
- **Project-scoped skills** — domain expertise is a *skill* force-loaded per task, not an agent.
- **The orchestrator (default) as the single front door** — it assigns, subagents/swarm execute, it verifies. One chat: the user's.

**Only PROMOTE a project to its own profile when it crosses ONE of these (not before):**
1. **Needs its own always-on interface** — a bot *other people* talk to, or that runs conversations independent of the user (HAJarvis lets Andrew live-debug HA in his own window).
2. **Strongly isolated domain memory** — its facts would pollute the orchestrator's hot tier or vice-versa (HA device maps belong in ha-bot, not default — proven this session when 7 HA cold-store facts were handed to ha-bot rather than pointered into default).
3. **Independent autonomous cadence** — its own cron / headless runs on its own schedule.
4. **Credential/tenancy isolation** — needs its own `.env`/keys walled off.

If it hits NONE, it's a board. Promotion is cheap to do later when the need is real, and expensive to maintain when it's speculative — so default to the board and let the project earn its profile. (When the user DOES want a fresh isolated bot for a domain that clears the bar, the `agent-handoff-package` skill is the bootstrap path.)

## DOCTRINE: BOUNDED AUTONOMY (Andrew, updated 2026-06-08 — supersedes manual-only)

**History matters here.** Andrew first chose manual dispatch (gate every spawn), then
DELIBERATELY REVERSED to bounded autonomy once he understood the scaling cost: *"I can't
helicopter everything you do... the constant approvals from the kanban stuff will simply
not be efficient cost wise."* Do NOT default back to per-dispatch approval — that reversal
is the standing doctrine and is persisted in his user-profile memory. The trust is in the
GUARDRAILS doing the safety work, not a human click:

- **Autonomous dispatch is ON** (`kanban.dispatch_in_gateway: true`, `auto_decompose: true`):
  the 60s tick spawns ready cards unattended. The safety net is structural, not manual:
  the **verifier gate** (catches bad/missing output — proven live, see below), the
  **concurrency cap** (`max_concurrent_children`, sized to host), **per-worker timeouts**
  (`child_timeout_seconds` / `--max-runtime`), `failure_limit` (auto-block after N fails),
  `dispatch_stale_timeout_seconds` (reclaim stuck workers), and **cron isolation**.
- **The distinction that still holds:** swarm DISPATCH is bounded-autonomous; **structural /
  infra / config / destructive changes STILL gate** with analysis+risks+rollback. Trust
  applies to swarm *execution*, not to changing the system.
- **Single-voice model.** User talks to the orchestrator (default profile); it routes to
  specialist profiles. User never addresses workers directly.
- Domain bots (HAJarvis, VoiceChanger) are **domain-locked** — do NOT conscript them as
  generic swarm hands; their SOUL/skills are scoped.

(Manual dispatch — `dispatch_in_gateway: false` + `hermes kanban dispatch --max <N>` —
remains the right tool for a user who wants no unattended spend, and doubles as cron
isolation. It is no longer Andrew's default, but keep it documented for other setups.)

## Building a swarm roster (the usual real gap)

A swarm needs N parallel workers + 1 verifier + 1 synthesizer as **distinct profiles**.
Most setups have one generic worker (`executor`) + an orchestrator (`default`) + domain
bots — i.e. effectively ONE usable generic worker and NO dedicated verifier. So adoption is
mostly **profile creation**, not config flipping. Recommended pod (RAM permitting):

- `swarm-worker-a/b/c` — lean/fast generic workers (DeepSeek-tier), count = concurrency cap.
  **Verified-good split (2026-06-08): workers on `deepseek-v4-flash`, verifier on
  `claude-opus-4-8`.** Flash workers ran 41–59s each vs 3–4min on `deepseek-v4-pro` — far
  faster/cheaper for parallel fan-out — while the expensive Opus spend concentrates exactly
  where quality matters (the gate). Synthesizer stayed on `deepseek-v4-pro`. ALWAYS verify a
  model id resolves before setting it (query the provider's `/v1/models` or point to a profile
  already running it) — never set an unverified model string, or every worker 401s on spawn.
- `swarm-verifier` — the one profile whose config GENUINELY differs: **skeptical,
  check-don't-build posture baked into its SOUL**, ideally a stronger model. Model it as a
  review gate (workers produce → verifier reviews, can `block` with comments → only on pass
  does synthesizer run). This is the one good idea worth stealing from GUI tools like
  vibe-kanban: a structured human-style review checkpoint, native via `comment`/`block`/`unblock`.
- `swarm-synthesizer` — composes the verified result into the deliverable.

Create them with the native tool (no hand-scaffolding):
`hermes profile create <name> --clone-from <src> --no-alias --description "<role>"`. The
`--description` is what the kanban **decomposer reads to route by role** — write it as the
role, not a label. Workers + synthesizer clone `executor` (DeepSeek-tier); verifier clones
the orchestrator profile (`default`, Claude/OAuth) so it gets the stronger model. Full
verified recipe + pitfalls in `references/swarm-profile-build-recipe.md`.

Honest tradeoff to state to the user: each profile is more config/SOUL/skills to keep in
sync — only worth it if recurring multi-track work actually exists. If 90% of work is
single-thread, the swarm sits idle and you've added maintenance surface.

### Build pitfalls (hit live, verified v0.16.0)

- **`patch`/`write_file` are HARD-BLOCKED from `config.yaml`** by the security write-guard
  (`Refusing to write to Hermes config file ... Agent cannot modify security-sensitive
  configuration`). This is by design — do NOT fight it. Use **`hermes config set <key>
  <value>`** instead, and **`hermes --profile <name> config set <key> <value>`** to scope to
  a profile (the `--profile` is a global flag *before* the subcommand). The guard does NOT
  block per-profile `SOUL.md` writes — those go through `write_file` normally (`.bak` first).
- **Cloning `executor` propagates a plaintext API key.** `executor`'s `model:` block carries
  a leaked plaintext `api_key` (a `mnfst_…`/`sk-…` value) while `provider: deepseek`. Every
  `--clone-from executor` inherits it. **Scrub it** on each DeepSeek clone:
  `hermes --profile <p> config set model.api_key ""` — auth still works because
  `api_key_env: DEEPSEEK_API_KEY` is set and each profile's `.env` carries that key. (Cosmetic:
  `config set ""` serializes as `''''` in raw grep but YAML parses it empty — functional.)
- **Do NOT scrub the verifier's inherited auth.** The verifier cloned from `default` carries
  Anthropic/OAuth auth (incl. `auth.json`) — working, and not the vestigial key. Least-
  astonishment: leave working auth alone; only scrub the known-vestigial DeepSeek-profile key.
- **Measured worker footprint is ~215–600MB**, lighter than the ~400–500MB estimate above —
  RAM is an even softer constraint than stated. Still probe live; don't assume.

### Live-operation bugs hit this session (verified v0.16.0 — read before running a swarm)

- **CONFIG-ON-DISK ≠ LIVE GATEWAY. `hermes config set` writes the file, but the running
  gateway holds the OLD config in memory** until restarted. This silently broke the
  cost governor: `dispatch_in_gateway: false` was set on disk, yet the live gateway (started
  earlier) kept auto-dispatching on its stale `true`. ANY kanban/dispatch/concurrency config
  change requires **`systemctl --user restart hermes-gateway.service`** to take effect. Verify
  with: gateway `ActiveEnterTimestamp` must be AFTER the config file's mtime. **Gotcha during
  restart:** the gateway can hang in `deactivating`/`stop-sigterm` for the full stop-timeout
  because the active session keeps it busy — systemd then SIGKILLs and brings up a fresh PID.
  Confirm the new `MainPID` differs from the old before claiming the restart landed. (This is
  a gated `systemctl restart` — present it as such.)
- **DELIVERABLES LIVE ON THE BLACKBOARD, NOT THE FILESYSTEM (RESOLVED — was a verifier design
  mismatch, NOT a worker bug).** Symptom: workers complete with rich handoff metadata but the
  verifier blocks every run as "artifacts missing from disk / fabricated." Reproduced twice,
  then root-caused: workers were correctly posting real analysis to the Kanban **blackboard**
  (`kanban_comment` + `kanban_complete` summary/metadata) exactly as the native
  `KANBAN_GUIDANCE` protocol intends, while the verifier SOUL had been (mis)written to check
  the **filesystem** for files that analysis work never produces. The independent fs checks
  (empty scratch dir, no `write_file` call, `find` → 0 hits) were all TRUE but measured the
  wrong thing — "no file on disk" was misread as "fabricated" when it meant "handed off via
  comment, as designed." **FIX: gate on blackboard SUBSTANCE, not files.** For research/analysis
  swarms the deliverable IS the handoff comment; only code/document tasks produce files (then
  the verifier checks the cited path). After the fix, run #3 passed clean end-to-end (verifier
  `{"gate":"pass"}` → synthesizer fired → all 5 cards `done`, ~4 min, substance-based verdict).
  **PITFALL: fix BOTH auto-injected layers — SOUL.md AND AGENTS.md.** A stale AGENTS.md saying
  "verifier checks your output against the filesystem / write your deliverable to a real file"
  silently contradicts a corrected SOUL (this exact trap hit live — grep every profile's SOUL
  *and* AGENTS.md for the old language and update both). If you ever build a CODE-GEN swarm
  where files genuinely matter, make a verifier VARIANT that checks disk — keep it separate
  from the analysis gate. Full resolved write-up + clean-run evidence in
  `references/worker-artifact-write-bug.md`.
- **Worker-honesty contract belongs in the worker SOUL** (necessary, and — combined with the
  blackboard-substance verifier above — now sufficient; clean run #3 proved it): "put real
  substance in your `kanban_comment` / `kanban_complete` handoff (the comment IS the
  deliverable for analysis work); only `write_file` to `$HERMES_KANBAN_WORKSPACE` if the task
  demands a concrete code/document artifact, and then verify it exists before citing it; never
  report a file/path/line-count/source you didn't actually produce; if you can't complete,
  `kanban_block` honestly — an honest block beats a fabricated 'done'." Give the 3 workers +
  synthesizer a shared autonomy-compatible `AGENTS.md` (the main agent's *discipline* —
  skills-scan, verify-before-done, tool-selection, anti-fabrication — with the interactive
  WRITE-GATE / recall-gate / approval mechanics REMOVED, since a leaf worker has no human in
  its loop to ask). **The shared AGENTS.md must use the blackboard model too** — an earlier
  version said "verifier checks the filesystem / write your deliverable to a real file" and
  silently contradicted the corrected SOULs (see the RESOLVED bug above). Leave the verifier
  OUT of that shared AGENTS.md — it keeps its distinct skeptical-gate SOUL. Profile AGENTS.md
  auto-injects by default (only `--ignore-rules` skips it); there is no per-file "present but
  don't inject" switch, so a non-injected rules file is invisible to a stateless worker —
  don't bother with that shape.

## Pitfall — the dispatcher SILENTLY drops cards with unknown assignees

A card assigned to a profile that doesn't exist on disk sits in `ready` forever — no error,
no autocorrect, no fallback. **Before planning a fan-out, discover the real roster**
(`hermes kanban assignees` lists profiles on disk + per-profile counts; `kanban init` also
prints them). Note snapshot/rollback profiles (`pre-update-*`, `stable-*`) show as
assignable but must NOT be workers — they run frozen old config.

## Single-host setup walkthrough (Andrew's stack)

For the concrete end-to-end build on one host — the 5-profile roster (3 distinct
`swarm-worker-a/b/c` + `swarm-verifier` + `swarm-synthesizer`), the **distinct-profiles-per-worker
rule** (each profile gets its own `state.db`, so spawning one worker N× risks `database is
locked` while N distinct profiles sidestep it by construction), the `executor` plaintext-key
scrub, the SOUL postures, and the manual-dispatch-only operating doctrine — follow
`references/swarm-profile-build-recipe.md` step by step. That reference is the canonical
walkthrough; the sections above are the reasoning behind each choice.

## Phased adoption (each later phase gates)

0. **Recon (no gate):** read `kanban-orchestrator`/`kanban-worker` contracts + the docs;
   confirm the exact `swarm` invocation.
1. **Board + validate (low-risk gate):** `kanban init` (idempotent); validate the graph
   via `--json` / `dispatch --dry-run` — no spawn.
2. **Build the roster (gated — profile creation):** template the pod; present each
   profile's config+SOUL before writing.
3. **One live bounded swarm (gated — spawns processes, spends tokens):** runtime-capped,
   results piped to the user via `hermes kanban notify-subscribe`.
4. **Doctrine + runbook (gated — config/memory):** set manual-dispatch, wire notifications,
   capture the operating runbook.

## Token economics — a swarm is 5–8× the cost of a solo run (state this up front)

The verification gate you *want* is what makes a swarm expensive. Be honest about the bill:

- **Per-job multiplier ≈ 5–8× a single-context run.** Inherent to the pattern, not the caps.
  Drivers: (a) every worker re-pays the full system prompt + auto-injected `KANBAN_GUIDANCE`
  + skills, every turn, × N agents; (b) the **blackboard re-read tax** (the big one) — the
  verifier ingests ALL worker output, then the synthesizer ingests the verified output
  again, so the same material is read 2–3×; (c) each agent runs multi-turn (orient → work →
  heartbeat → complete), not one call.
- **Raising the concurrency cap is COST-NEUTRAL per job.** `max_concurrent_children` is a
  *concurrency* limit, not a volume limit — a 3-worker swarm burns the same tokens at cap 3,
  6, or 8. Higher cap = same total tokens spent *faster* (throughput/latency), not more. So
  "6 vs 8" is a throughput decision, never a cost decision. The cost decision is "how many
  swarms / how wide a fleet do I dispatch."
- **Two currencies.** Workers + synthesizer + decomposer on DeepSeek-tier = **real $/token**,
  scales with worker count + blackboard size. The verifier on a Claude OAuth-bypass = **flat
  subscription but rate-limited** — under many concurrent swarms the *verifier* becomes the
  Claude-rate bottleneck before DeepSeek $ does.
- **The one knob that silently inflates spend:** `kanban.auto_decompose_per_tick` combined
  with the autonomous tick — it fans out more tasks automatically, on a timer, unattended.
  `max_concurrent_children` is benign for cost; `auto_decompose` + autonomous dispatch is the
  amplifier. **Manual dispatch is the cost governor**, far more than any cap number. Pair any
  cap raise with `--max-runtime` (caps a stuck worker's bleed) and `dispatch --max` (bounds
  fan-out per pass).
- **Don't fabricate a token number.** Measure run #1: `hermes kanban runs` + per-task worker
  logs give real token/$ on the user's actual task shapes. Make "report real spend on the
  first swarm" an explicit Phase-3 deliverable.

## Speedup — there is NO single "%", and "10X" is marketing

Three different axes get conflated. Give the user the model, not a made-up number:

- **Per-task latency (Amdahl-capped).** Only the worker phase parallelizes; decompose →
  verifier → synthesizer are sequential by design. A 60%-parallel job across 3 workers ≈
  `1/(0.4+0.6/3)` ≈ **1.67× (~40% faster)**; 80%-parallel ≈ **~2.1× (~52%)**. That's the
  realistic ceiling per task — never 3×, because the gate is sequential. Single-thread work
  ("fix this file") gets **~0%, slightly negative** (you added decompose+gate overhead).
- **Throughput (the real multiplier).** For a *backlog* of independent tasks / fleet work,
  throughput scales near-linearly with worker count **until API rate limits**, so **4–8×
  tasks/hour** — but only if a wide backlog actually exists.
- **Calendar time (what "autonomous" actually buys).** Autonomy doesn't speed any single
  task; it removes human-trigger latency so a backlog runs unattended/overnight. The "10X"
  claims are calendar compression of a backlog, not per-task speed.

Bottom line for an interactive, mostly single-track, human-in-the-loop user: realistic
per-interaction speedup is **modest (tens of %, sometimes negative)**. The swarm pays off
only if the user *changes how they work* toward multi-track / fleet / unattended-backlog jobs.

## Config knobs + cron isolation

The concurrency caps ship tuned for a small box; on a resized host they artificially
throttle. The real knobs (verified v0.16.0):

- `delegation.max_concurrent_children` — **global pool** for ALL workers (kanban workers
  spawn as delegation children). NOT partitioned by source.
- `delegation.max_spawn_depth` — keep at 1 (children can't spawn grandchildren). A guardrail.
- `kanban.auto_decompose_per_tick` — match to the cap so the wider pool stays fed (inert if
  dispatch is off — only fires on the tick).
- `kanban.dispatch_in_gateway` / `kanban.dispatch_interval_seconds` — the autonomous tick.

Sizing the cap: at 8 vCPU, **API rate limits bite before RAM or CPU** above ~6 concurrent
workers — 7–8 simultaneous DeepSeek calls risk 429s, and backoff can make aggregate
throughput *drop*. So more workers past ~6–8 is counterproductive, not "using the box."
Idle free RAM is NOT waste — healthy headroom is the point of an upgrade; never size to
"fill RAM." Recommend cap 6 for a single swarm + slack; 8 only if the user confirms
**concurrent multi-swarm or fleet** work (then 2 swarms' worker phases = 6, and 8 lets their
verifiers overlap instead of serializing).

**Preventing cron from using the swarm** — two leak paths:
1. An agent-driven cron on a profile wired with kanban skills (e.g. `executor`) could call
   `kanban_create`/dispatch. Restrict via `enabled_toolsets` minus `kanban` on those crons.
2. The autonomous dispatcher auto-spawns *any* ready card a cron drops. **Killing the tick**
   (`dispatch_in_gateway: false`) is the master switch — cron can stage cards but zero
   workers spawn until a human runs `hermes kanban dispatch`. Manual dispatch thus doubles as
   cron isolation. Honest limit: the concurrency *pool* stays global (no per-source reserve),
   but manual dispatch makes that contention theoretical — you never run a swarm while a
   surprise cron fan-out fires, because nothing auto-spawns.

See `references/config-knobs-and-cost.md` for the verified key list and the cost/speedup math.

## Evaluating third-party kanban / orchestration tools

Apply the review-before-install discipline: **verdict first, then security/overlap/footprint.**
Worked example — `BloopAI/vibe-kanban` (June 2026): VERDICT = don't install.
- **Dealbreaker:** the project is **sunsetting** (README banner + shutdown announcement;
  last commit stale). Never base core orchestration on a tool the maintainers are winding down.
- **Wrong shape even otherwise:** it's a **localhost web GUI** (Rust+Node+pnpm) wrapping
  *external* coding-agent CLIs (Claude Code, Codex, Cursor…) for git diff/PR review on one
  workstation. A headless VPS reached over chat can't use a `127.0.0.1` browser UI, and its
  domain is git-coding workflows, not general multi-agent work.
- **Redundant:** Hermes Kanban already provides the durable board/worker/dispatcher natively.
- **Telemetry:** ships PostHog analytics (build-time keys) — counter to minimal-footprint posture.
- **Cherry-pick, don't install:** the only worthwhile idea was its diff-review-with-comments
  gate → map onto the `swarm-verifier` profile + native `comment`/`block`/`unblock`. Capture
  as an attributed `~/.hermes/references/` note, never adopt upstream.

See `references/vibe-kanban-evaluation.md` for the full teardown.
