---
name: kanban-swarm-setup
description: Set up and operate Hermes native Kanban swarms for Andrew's multi-host setup — profile roster, dispatch doctrine, and the manual-only operating rule. Use when building swarm profiles, running swarms, or deciding kanban vs delegate_task.
version: 1.0.0
platforms: [linux]
environments: [kanban]
metadata:
  hermes:
    tags: [kanban, swarm, multi-agent, orchestration, profiles]
    related_skills: [kanban-orchestrator, kanban-worker]
---

# Kanban Swarm Setup (Andrew's stack)

Kanban is a **native Hermes feature** (NOT third-party). Board lives at `~/.hermes/kanban.db` (initialized 2026-06-08). Verified against live install v0.16.0.

## When to use Kanban vs delegate_task
- **delegate_task**: ephemeral, in-turn, dies if parent turn interrupts. Use for short parallel bursts where the result returns into the parent's context.
- **Kanban**: durable, cross-session, survives restarts/compaction. Use when work crosses agent boundaries, must outlive a turn, or needs a human-in-the-loop gate.

## The swarm command
```
hermes kanban swarm "<goal>" \
  --worker PROFILE:TITLE \   # repeatable; each spawn = its own OS process + workspace
  --verifier PROFILE \
  --synthesizer PROFILE
```
Graph: N parallel workers → verifier (wakes after all workers finish) → synthesizer (wakes only after verifier signs off). NO `--dry-run` on swarm (only `dispatch` has it); validate with `--json` or `dispatch --dry-run` after cards exist.

## Profile roster (5, not 3) — WHY
Each profile has its **own `state.db`**. Spawning ONE worker profile N× concurrently = N processes hammering one SQLite state.db → "database is locked" risk. **Distinct `swarm-worker-a/b/c` each get own state.db → contention gone by construction.** At 30GB+ RAM the extra-profile cost is noise, so 5 beats 1-spawned-N. (At 8GB it was the opposite — RAM was the constraint.)

| Profile | Clone from | Model | Role |
|---|---|---|---|
| swarm-worker-a | executor | deepseek-v4-pro | research/investigation |
| swarm-worker-b | executor | deepseek-v4-pro | architecture/design |
| swarm-worker-c | executor | deepseek-v4-pro | implementation |
| swarm-verifier | default | Sonnet/Opus (OAuth) — stronger on purpose | skeptical review gate; `block`s with comments, does NOT do the work |
| swarm-synthesizer | executor | deepseek-v4-pro | assembles verified output, composes (no re-research) |

3 workers = matches `delegation.max_concurrent_children: 3`.

## Build steps (GATED — profile dir writes)
```
hermes profile create swarm-worker-a --clone-from executor --description "..."
# ...b, c, verifier (--clone-from default), synthesizer
```
`--description` is what the **kanban decomposer uses to route by role** — write it carefully. executor already wires `kanban-orchestrator` + `kanban-worker` skills, so clones inherit the swarm toolset.
Then: SOUL edits on verifier (skeptical/check-don't-build posture — borrowed from vibe-kanban's diff-review gate) + synthesizer (composer). `.bak` first.

## PITFALLS
- **Dispatcher silently drops cards assigned to non-existent profiles** — they sit in `ready` forever. Verify roster with `hermes kanban assignees` before dispatch.
- **executor's config.yaml had a leaked plaintext `api_key: mnfst_...`** in the `model:` block (vestigial, provider is deepseek). Scrub it from clones so it doesn't propagate.
- **NEVER assign tasks to `stable-2026-06-02` or `pre-update-2026-06`** — those are rollback snapshots, not workers.
- Domain bots (ha-bot, voice-changer) are domain-locked — don't use as generic swarm workers.

## OPERATING DOCTRINE — Andrew's rule
Dispatcher runs in the gateway, ticks every 60s by default (`kanban.dispatch_interval_seconds`). Andrew wants **MANUAL dispatch only** — `hermes kanban dispatch --max N` on his greenlight — NOT the autonomous tick (his no-silent-trigger rule). Workers are real processes spending real tokens; always cap with `--max-runtime`. Pipe results to Telegram via `notify-subscribe` so he stays single-point-of-contact.

## Rejected alternative
vibe-kanban (BloopAI) — REJECTED: it's sunsetting + it's a localhost web GUI for git-coding agents (wrong shape for headless chat-driven VPS). Only its diff-review-gate ergonomics were borrowed into swarm-verifier. Don't install.

## Rollback
`hermes profile delete swarm-worker-a swarm-worker-b swarm-worker-c swarm-verifier swarm-synthesizer` — clean, zero impact on existing profiles. SOUL edits have `.bak`.
