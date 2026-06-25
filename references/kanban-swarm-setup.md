# Hermes Kanban Swarm — Reference

**Status:** Production-ready for research/analysis swarms (verified 2026-06-08, clean end-to-end run).
**Host:** `ubuntu-8gb-hil-1` (worker box) — 32GB RAM / 8 vCPU after upgrade.

---

## What this is

A durable, autonomous, self-verifying multi-agent swarm built on native Hermes Kanban (`hermes kanban`). You give the orchestrator a goal; it decomposes onto a SQLite board; named worker profiles run in parallel as isolated OS processes; a skeptical verifier gates their combined output; a synthesizer assembles the final deliverable. Survives restarts and context compaction (unlike `delegate_task`, which is in-turn and ephemeral).

## The 5-profile pod

| Profile | Model | Role | Why this model |
|---|---|---|---|
| `swarm-worker-a` | deepseek-v4-flash | Parallel worker — research | Cheap, fast, high-volume fan-out |
| `swarm-worker-b` | deepseek-v4-flash | Parallel worker — architecture/tradeoffs | "" |
| `swarm-worker-c` | deepseek-v4-flash | Parallel worker — implementation/recommendation | "" |
| `swarm-verifier` | claude-opus-4-8 | Skeptical gate — blocks or passes | Strong reasoning to catch what cheap workers miss |
| `swarm-synthesizer` | deepseek-v4-pro | Assembles verified output | Mid-tier; composes, doesn't re-research |

Each profile has its **own `state.db`** → no SQLite write contention (the reason for 3 distinct workers, not one spawned 3×).

## Cost/quality logic
Cheap flash workers do the parallel grunt work; the expensive Opus token spend is concentrated at the **gate**, where quality matters most. Verified timing: flash workers 41–59s each (parallel), Opus verifier ~1m, pro synthesizer ~2m → **~4 min end-to-end**.

## The critical design rule: blackboard, not filesystem

**Deliverables for research/analysis swarms live on the Kanban blackboard** (structured `kanban_comment` posts + `kanban_complete` summary/metadata), NOT as files on disk. This is how the native `KANBAN_GUIDANCE` protocol (hardcoded in `agent/prompt_builder.py`, auto-injected into every worker) is designed to work.

**Root-cause lesson (cost two failed runs):** An early verifier SOUL checked worker output *against the filesystem*. Workers correctly posted real analysis to the blackboard but wrote no files → verifier blocked every run as "fabricated." The workers were fine; the verifier was checking the wrong place. **Fix:** verifier gates on blackboard *substance*; workers put real content in comments and only write files when the task explicitly demands a code/document artifact.

> If you ever build a **code-generation** swarm (deliverables genuinely are files), make a verifier *variant* that checks disk. The current verifier is tuned for analysis/research handoffs.

## Configuration (on `ubuntu-8gb-hil-1`, default profile config.yaml)

```
delegation.max_concurrent_children: 8     # was 3; raised post-32GB-upgrade
delegation.max_spawn_depth: 1             # children can't spawn grandchildren
kanban.dispatch_in_gateway: true          # autonomous 60s tick
kanban.auto_decompose: true
kanban.auto_decompose_per_tick: 8
kanban.failure_limit: 2                   # auto-block after 2 failed attempts
kanban.dispatch_stale_timeout_seconds: 14400  # reclaim stuck workers
```

**Bounded-autonomy doctrine:** dispatch is autonomous (gateway tick), NOT per-click approved. Safety comes from guardrails, not a human click: verifier gate + concurrency cap + per-worker timeout + failure_limit. Rationale: per-dispatch approval doesn't scale and is cost-inefficient. (Structural/destructive infra changes STILL gate normally — trust applies to swarm execution only.)

## How to run a swarm

```bash
# Stage the graph (creates cards; autonomous tick dispatches within 60s)
hermes kanban swarm "<goal>" \
  --worker swarm-worker-a:Research \
  --worker swarm-worker-b:Architecture \
  --worker swarm-worker-c:Recommendation \
  --verifier swarm-verifier \
  --synthesizer swarm-synthesizer \
  --idempotency-key "<unique-key>"        # dedup: repeat calls return same id

# Watch
hermes kanban list                         # board state
hermes kanban stats                        # per-status counts
hermes kanban runs <task_id>               # attempt history + elapsed + outcome
hermes kanban show <task_id>               # full task + comments (the blackboard)
hermes kanban log <task_id>                # worker's full session log
```

## Operational gotchas (learned the hard way)

1. **Config changes need a gateway restart to take effect.** The running gateway holds config in memory. Changing `config.yaml` does nothing until `systemctl --user restart hermes-gateway.service`. (This is why an early "manual dispatch" setting silently didn't enforce — the live process still had the old autonomous config.)
2. **The gateway restart can hang in `stop-sigterm`** if a session is active on it (the restart kills the very process running your session). It SIGKILLs at the stop-timeout, then a fresh process starts. Expect a brief interruption.
3. **Dispatcher silently skips cards with unknown assignees.** A card assigned to a profile that doesn't exist sits in `ready` forever — no error. Check `hermes kanban assignees` first.
4. **Cron isolation:** no agent cron has the `kanban` toolset (whitelist `enabled_toolsets` excludes it); no-agent script crons can't call tools at all. Cron cannot trigger a swarm.
5. **Don't grep the install tree with loose patterns** — `node_modules` has 15MB minified JS files that will blow up tool output. Use `file_glob` / narrow paths.

## Verifier behavior reference (proven)
- **Blocks** when handoffs are fabricated/hollow/missing (runs 1–2: blocked on missing files).
- **Passes** when blackboard substance is real and complete (run 3: `{"gate": "pass"}` → synthesizer fired).
- Block comments are actionable (name the exact defect), never "needs more detail."

## Rollback / teardown
- Delete the pod: `hermes profile delete swarm-worker-a swarm-worker-b swarm-worker-c swarm-verifier swarm-synthesizer`
- Revert to manual dispatch: `hermes config set kanban.dispatch_in_gateway false` **then restart gateway**.
- SOUL/AGENTS/config backups: `.bak-*` and `.bak-A-*` in each profile dir.
