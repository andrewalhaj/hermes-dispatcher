# Kanban/swarm config knobs, cost & speedup (verified v0.16.0)

Session-derived reference for the operator-side numbers. Always re-probe live before
promising — these are the verified shapes, not guarantees about the user's current values.

## Verified config keys

```yaml
delegation:
  max_concurrent_children: 3   # GLOBAL pool for all workers; kanban workers spawn as
                               # delegation children. NOT partitioned by source (cron vs swarm
                               # draw from the same budget).
  max_spawn_depth: 1           # keep at 1 — children can't spawn grandchildren. Guardrail.

kanban:
  dispatch_in_gateway: true        # the autonomous tick. false = manual-only (master switch /
                                   # cron isolation).
  dispatch_interval_seconds: 60    # tick period when dispatch_in_gateway: true
  auto_decompose: true
  auto_decompose_per_tick: 3       # how many goals the decomposer fans out per tick. Match to
                                   # the concurrency cap so the pool stays fed. Inert if
                                   # dispatch is off (only fires on the tick). THIS + autonomous
                                   # tick is the silent spend amplifier.
  failure_limit: 2                 # auto-block a card after N consecutive failed attempts
  max_in_progress_per_profile: null
  dispatch_stale_timeout_seconds: 14400
```

CLI cost/runtime guards:
- `hermes kanban dispatch --max N` — bound spawns per pass (cost governor under manual dispatch)
- `hermes kanban create ... --max-runtime 30m` — cap a stuck worker's token bleed
- `hermes kanban dispatch --dry-run` — preview without spawning (swarm itself has NO --dry-run)
- `hermes kanban runs` + per-task worker logs (`<kanban-root>/kanban/logs/`) — pull REAL token/$

## Sizing the cap (8 vCPU example from this session)

- Measured worker footprint: **~215–600MB resident each** (lighter than the ~400–500MB rule of
  thumb; still treat 400–500 as the planning number).
- At 30GB free, even 8 workers ≈ 3–5GB ≈ ~14–18% RAM. **RAM is never the ceiling at these counts.**
- Real ceiling at 7–8 concurrent on 8 vCPU = **API rate limits, then CPU latency-creep**, not RAM.
  7–8 simultaneous DeepSeek-v4-pro calls risk 429s; backoff can make aggregate throughput *drop*.
- **Recommend cap 6** for one swarm + slack. **Cap 8 only for confirmed concurrent multi-swarm /
  fleet** (2 swarms' worker phases = 6; 8 lets their verifiers overlap instead of serializing).
- Going past 8 is theater — it neither uses RAM usefully nor adds throughput; it adds 429 risk.
- **Idle free RAM is not waste.** Healthy headroom is the upgrade's value; never size to "fill RAM."

## Cost model (the 5–8× multiplier)

A swarm ≈ 5–8× the tokens of doing the task in one context. Drivers:
1. Per-worker system prompt + `KANBAN_GUIDANCE` + skills, re-paid every turn × N agents.
2. **Blackboard re-read tax** (largest): verifier ingests all worker output → synthesizer
   ingests verified output again → same material read 2–3×.
3. Multi-turn per agent (orient/work/heartbeat/complete), not one call.

Two currencies: workers+synthesizer+decomposer = real $/token (DeepSeek-tier); verifier on a
Claude OAuth bypass = flat subscription but rate-limited (becomes the bottleneck under many
concurrent swarms). Raising the concurrency cap is **cost-neutral per job** — same tokens,
spent faster. Spend scales with *how many/how wide* you dispatch, governed by manual dispatch
+ `--max` + `--max-runtime`.

## Speedup model (no single %)

- Per-task (Amdahl): only worker phase parallelizes. 60%-parallel/3 workers ≈ 1.67× (~40%);
  80% ≈ 2.1× (~52%). Ceiling, never 3×. Single-thread work ≈ 0% or slightly negative.
- Throughput: backlog/fleet ≈ 4–8× tasks/hr until API limits — only if a wide backlog exists.
- Calendar: autonomy doesn't speed a task; it removes human-trigger latency (overnight runs).
  The "10X" marketing = calendar compression of a backlog, not per-task speed.

## Cron isolation

1. Restrict agent-driven crons with `enabled_toolsets` minus `kanban`.
2. `dispatch_in_gateway: false` = master switch: cron can stage cards, but nothing spawns until
   a human dispatches. Manual dispatch doubles as cron isolation. Caveat: the concurrency pool
   stays global (no per-source reserve) — manual dispatch makes that contention theoretical.
