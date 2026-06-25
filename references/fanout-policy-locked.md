# Fan-Out Routing Policy — Locked

**Date:** 2026-06-19
**Status:** LOCKED. Supersedes fanout-sizing-measurement-report.md, decomposition-revalidation-report.md, and fanout-policy-closeout.md. Those documents are measurement lineage; this is the policy.
**Re-open trigger:** §6 re-open conditions only. No constant re-opens before it becomes load-bearing.

---

## 1. Stop decision — honest rationale

Three measurement cycles have crossed the threshold the policy exists to guard: measurement costing more than the error it removes.

**The single sentence that carries the whole decision:** no constant here gates anything at runtime yet. Until a constant is wired into a live routing gate, its precision is premature. Lock provisional now; measure each constant at the moment it becomes load-bearing, not before.

This does not depend on any per-task argument. It covers everything.

---

## 2. Mechanism separation (the conceptual fix — carry into all future reasoning)

Three distinct routing decisions with distinct governing constants:

**Inline** — execute in the parent. Default for low chunk counts and light reads.

**Isolate (R\*, width=1)** — delegate a *single* chunk when read volume is high, to protect the parent window. Governed by R\* (read volume). Independent of chunk count. This is what justifies *delegation in general* — it applies even when chunk_count=1.

**Fan-out (K, width≥3)** — split into N *parallel* chunks. Its marginal benefit over isolate-at-1 is *parallel speed only* — a single subagent handling all N chunks already gives the full isolation benefit. Therefore fan-out is governed by **speed**, not isolation.

**The correction this separation enforces:** isolation justifies *delegating*; it does not justify *parallelism*. K is a speed threshold. Any argument that K is "isolation-set" is wrong — isolation sets the decision to delegate, and width=1 captures it fully.

---

## 3. K — corrected derivation

Because fan-out's only marginal benefit over single-chunk isolation is parallel speed, K is speed-governed. The break-even is:

```
Fan-out wins when: (N - 1) × per_chunk_time > delegation_tax
Therefore: N* ≈ (delegation_tax / per_chunk_time) + 1
```

Using the observed ~140s floor (n=2, in-session; shape assumed fixed pending T2):

| Per-chunk inline time | N\* (fan-out break-even) |
|---|---:|
| ~20s (small chunk) | **~8** |
| ~60s (medium chunk) | **~3** |
| ~120s (large chunk) | **~2** (isolate-at-1 usually dominates) |

**Earned answer: K is size-aware, not flat.**

- Small chunks (≤30s inline): fan-out for speed at ~8+
- Medium chunks (~60s inline): fan-out at ~3
- Large chunks (≥120s inline): fan-out rarely worth it; prefer isolate-at-1

**If a flat constant is operationally required:** ship **K=3, labeled explicitly as a simplification correct for medium chunks, over-fanning small ones.** That tradeoff is acceptable. It is a simplicity choice, not an earned threshold, and must not be presented as the latter.

**What the 60% demand rate means:** fan-out-worthy objectives are common — this supports running the fan-out path regularly. It does not set K. Commonality ≠ threshold.

---

## 4. The one genuine prerequisite before any runtime gate

The entire speed branch rests on one untested assumption: the fixed tax *shape* (R²≈0.11, confirmed at ~26s proxy) holds at the real ~140s `delegate_task` scale. If at real scale the tax scales with read volume instead of staying fixed, parallelism stops amortizing cleanly and every N\* shifts.

**T2 is required before speed-aware fan-out ships as a runtime gate — and only then.**

T2: n≥8 minimal/no-read `delegate_task` delegations through the real mechanism. Confirms (a) the actual floor at that scale and (b) that the fixed shape holds (low R² vs read volume). Cheap. Not needed to lock policy on paper. Required before live routing on speed.

---

## 5. Final policy table

| Constant | Value | Grounding | Honest label |
|---|---|---|---|
| **K (fan-out threshold)** | Size-aware: ~8 small / ~3 medium / ~2 large. Flat **K=3** acceptable as labeled simplification | N\*=tax/t+1 derivation from measured floor + per-chunk times | Derived, size-aware. Flat-3 is a simplification, not earned |
| **Speed N\*** | ~tax/t + 1 per row above | M1/M2 in-session, n=2 | Measured shape at proxy scale; floor assumed fixed at real scale |
| **Delegation tax** | ~140s floor, fixed shape | Observed n=2; shape confirmed at ~26s proxy only | Observed. Shape at 140s: assumed, not confirmed |
| **Isolation trigger (R\*)** | 50K parent read tokens | Reasoned default; M4 not run | Reasoned default |
| **W\_cap** | 5 | p90 of M3 write distribution (biased lower bound) | p90-observed; efficiency unmeasured |
| **Demand rate L3≥3** | ~60% of multi-part objectives | Blinded decomposers, n=10, directional, no CI | Directional only — valid to say "fan-out is common," invalid to set a threshold from it |
| **Demand rate L3≥8** | ~10% | Same, same caveats | Directional only |

---

## 6. Re-open triggers (not a backlog — each fires when load-bearing)

| Measurement | Re-opens when |
|---|---|
| **T2** (real delegate_task floor + shape, n≥8) | Before shipping speed-aware fan-out as a live runtime gate |
| **M4 / R\*** | Before shipping the isolation trigger as a live runtime gate; measure on live parent-context budgets, not synthetic sweep |
| **M5 / W\_cap efficiency** | When a genuine ≥8-domain objective occurs; natural experiment beats a constructed width-2/4/8 synthetic run |
| **T1 (CI on ~60%)** | Only if demand rate is ever promoted from "fan-out is common" to a threshold-setter — which it must not be |

Nothing re-opens before its trigger. No measurement is a standing backlog item.

---

## 7. Limitations (carried into the lock)

- Size-aware N\* rests on n=2 per-chunk-time observations; treat each break-even as a range, not a point.
- ~140s floor is observed, not measured at n≥8; its *shape* at that scale is assumed, not confirmed (the T2 gate).
- Demand distribution is n=10, directional — valid only to confirm fan-out is common, never to set a constant.
- W\_cap=5 inherits the M3 write bias; it is a p90-observed cap, not an efficiency ceiling.
- R\* and K are coupled: if R\* is later measured well above 50K, the case for delegating small read-light multi-chunk objectives weakens. Re-check K's small-chunk behavior whenever R\* lands.

---

## 8. Measurement lineage (for auditability)

| ID | What | Status | n | Notes |
|---|---|---|---|---|
| M7 | Delegation model confirmation | Done | n=2 + config | Sonnet/Opus Anthropic; SOUL corrected |
| M3 | Write-path decomposition | Done, retired as biased lower bound | 156 sessions | Measures executed writes, not demanded scope |
| D1/D2 | Blinded demand decomposition | Done | n=10, 2 raters | 70% exact L3 agreement; directional |
| D3 | Tax shape at proxy scale | Done | n=5 | R²=0.11, fixed-dominant at ~26s harness |
| M1/M2 | Per-chunk time + tax floor | Observed | n=2 | ~140s floor, 15–120s chunk range |
| T3 | Economic K derivation | Done | Derivation | This document, §3 |
| T2 | Real delegate_task floor + shape | Deferred | — | Required before speed-gate ships |
| M4 | R\* isolation trigger | Deferred | — | Required before isolation-gate ships |
| M5 | W\_cap efficiency | Deferred | — | Triggered by natural ≥8-domain objective |
| T1 | CI on 60% demand rate | Deferred | — | Only if demand rate ever sets a threshold |

---

## 9. Operational summary (one paragraph)

Delegate when read volume is high (parent protection, independent of chunk count, governed by R\*=50K default). Fan out when chunk count ≥ N\* for the chunk size: ~8 for small tasks, ~3 for medium, skip for large. If operational simplicity requires a flat threshold, use K=3 and label it a medium-chunk simplification. Run T2 before wiring any of this to a live speed gate. Measure R\* and W\_cap at the moment they become live-gate inputs, not before. The recursion ends here.
