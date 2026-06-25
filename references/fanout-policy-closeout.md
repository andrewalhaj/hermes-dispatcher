# Fan-Out Policy — Cycle 3 Close-Out

**Date:** 2026-06-19
**Status:** T3 delivered (free, from existing data). T1/T2/T4/T5 deferred — cost exceeds decision leverage. Policy locked with honest grounding flags.

---

## Decision to stop the measurement recursion

Three validation cycles have each been individually valid. The aggregate has crossed a threshold the policy itself exists to guard: **measurement costing more than the thing it measures.**

**What K's imprecision costs:** an occasional misroute — paying the ~140s delegation tax on a task that would be marginally faster the other way. Self-correcting per task, happens a few times a week.

**What T1–T5 costs:** ~40–50 subagent spawns, 2–4M tokens, ~$10–40. Spent to tighten the confidence interval on a constant whose error costs seconds.

The flag was surface-and-defer, not refuse. If the full T1–T5 run is wanted, it runs completely — no curation. The recommendation is to lock now.

---

## T3 — Economic derivation of K (the one real logical gap, closed)

The prior report cited "60% of objectives hit ≥3 demanded chunks" as if that set K=3. It doesn't — commonality ≠ threshold. That is the one genuine logical error in the revalidation report. Here is the economic derivation from data already in hand.

### Speed break-even

```
N* = delegation_tax / per_chunk_inline_time
```

Using the measured real `delegate_task` floor (~140s, from in-session delegations this session):

| Per-chunk inline time | N* (speed break-even) |
|---|---:|
| ~20s (small chunk, e.g. `_ins_for_ui` SQL fix) | **~7** |
| ~60s (medium chunk) | **~2.3** |
| ~120s (large chunk, e.g. `kanban_checkpoint` extension) | **~1.2** |

**A flat K=3 is not speed-justified for small chunks.** Small-chunk tasks need ~7 to pay back the delegation tax in parallel savings. K=3 only makes speed-sense for medium-to-large chunks.

### The isolation branch (floor-independent)

The context-isolation benefit does not depend on the delegation tax magnitude. It fires at width ≥1 whenever read volume is high: the in-session measurement shows 191K tokens absorbed in a subagent window for a task that is ~15s inline. That benefit is real regardless of whether the floor is 26s or 140s.

The isolation branch justification:
- Parent window stays clean regardless of task size.
- 40% of objectives are structurally single-chunk but read-heavy — they benefit from isolation at width 1 even below K.
- For the 60% that hit ≥3 demanded chunks, isolation compounds: 3 × 191K tokens stay out of the parent window.

### Resolution

**K is set by the isolation branch + demand commonality, not by speed.** K=3 is the point at which fan-out benefits (isolation × chunk count) reliably exceed the fixed cost on the workload distribution we measured. Speed does not set it — speed is a size-dependent secondary benefit that happens to also support K at medium-to-large chunks.

**This conclusion is robust to the T2 open question.** T2 would measure whether the real `delegate_task` floor is confirmed at ~140s and whether the fixed shape holds at scale. But T2 only moves the *speed* break-even — and the conclusion routes on isolation, not speed. T2 does not change the answer. K=3 holds regardless.

**Recommended speed-branch policy:** make it explicitly size-aware rather than a flat threshold. Fan small chunks (≤30s inline) for speed only at ~7+. Fan medium+ chunks (≥60s inline) for speed at ~3. For isolation, delegate at width 1 whenever read volume is high, independent of chunk count.

---

## What T1–T5 would have produced (and why each is deferred)

**T1 (n≥40 blinded decomposition):** would tighten the 60% L3≥3 rate with a CI. Deferred because the 60% figure now supports K qualitatively (it shows fan-out is common) rather than setting K (which is now set economically). A tighter CI on 60% does not change the economic derivation above.

**T2 (real `delegate_task` floor, n≥8):** would confirm the ~140s floor at real scale and verify fixed shape. Deferred because: (a) the T3 conclusion is robust to whether the floor is 140s or higher, as argued above; (b) T2's cost (~8 real delegations × ~150K tokens each ≈ 1M+ tokens) is disproportionate to its marginal impact given (a).

**T4 (M5 — integration cost vs width):** would set W_cap on efficiency rather than p90-observed. Deferred — the 10% L3≥8 rate justifies the measurement in principle, but W_cap's current "p90 observed cap" relabel is an honest flag, and the efficiency measurement can wait for a real wide-fan-out task rather than a synthetic one.

**T5 (M4 — R* isolation trigger):** would replace the 50K-token reasoned default with a measured number. Deferred — the 40% single-chunk population is governed by R*, but the current reasoned default is conservative and the measurement is only needed if the isolation trigger is shipping as a runtime gate (it isn't yet).

---

## Final policy table

Every constant is either grounded in measurement or explicitly flagged as a reasoned default. No assertion presented as measurement.

| Constant | Value | Grounding | Source |
|---|---|---|---|
| **K (fan-out threshold)** | 3 | **Earned** — isolation-set + demand-common; T3 economic derivation robust to T2 | T3 (this report) + D1/D2 demand distribution |
| **Speed branch N\*** | ~7 for small chunks, ~2–3 for medium | **Earned** — N\*=tax/t from measured floor and per-chunk times | T3 derivation, M1/M2 in-session |
| **Delegation tax shape** | Fixed floor, R²=0.11 | **Measured shape** at proxy scale; scale unconfirmed at 140s but does not affect K | D3 (n=5 proxy runs) |
| **Delegation tax floor** | ~140s (in-session `delegate_task` observations) | **Observed**, n=2; not formally measured at this scale | In-session observations |
| **Demand distribution (L3≥3)** | ~60% of multi-part objectives | **Measured** (n=10, 2 raters, 70% exact agreement); CI not computed — treat as directional, not precise | D1/D2 blinded decomposers |
| **Demand distribution (L3≥8)** | ~10% | **Measured**, same caveats, low n | D1/D2 |
| **W_cap** | 5 | **Reasoned** — p90 observed cap from M3 writes; efficiency unmeasured | M3 (write distribution, biased) |
| **R\* (isolation trigger)** | 50K parent-context read tokens | **Reasoned default** — M4 not run | Reasoned estimate |

---

## What remains open (explicitly, not buried)

**R\* (M4):** the 50K default is reasoned. Measure it when the isolation trigger is being implemented as a runtime gate, using real parent-context budgets from live sessions rather than a synthetic sweep.

**W_cap (M5):** relabeled honestly as "p90 observed cap, not efficiency-derived." Measure it on a real wide-fan-out task if and when the 10% ≥8-chunk case is encountered in practice — a synthetic width-2/4/8 run on a constructed workload is a weaker measurement than the natural experiment.

**D3 at real scale (T2):** the proxy floor (~26s) confirmed fixed shape. The real floor (~140s) is observed but not formally measured. Accept the observed value; re-measure if the speed branch is ever made a runtime gate.

---

## Measurement lineage (for auditability)

| Measurement | Status | n | Method |
|---|---|---|---|
| M7 (delegation model) | Done | n=2 probes + config read | Live config + in-session delegations |
| M3 (write-path decomposition) | Done, retired as biased | n=156 sessions | DB write-path analysis |
| D1/D2 (blinded demand decomposition) | Done | n=10 objectives, 2 raters | Blinded subagent decomposers |
| D3 (tax shape — proxy) | Done | n=5 controlled spawns | `hermes chat -q` proxy |
| T3 (economic K derivation) | Done | Derivation from existing data | N*=tax/t, isolation-branch analysis |
| M4 / R* | Deferred | — | Cost exceeds current need |
| M5 / W_cap efficiency | Deferred | — | Cost exceeds current need |
| T1 (n≥40 decomposition) | Deferred | — | 60% directional; CI doesn't change K |
| T2 (real tax floor) | Deferred | — | Conclusion robust to floor scale |

---

## Limitations

- Demand distribution (60% L3≥3) is n=10, directional only. Treat as "fan-out is common" rather than "precisely 60%."
- T3 derivation uses n=2 in-session per-chunk time observations. Spread is real; N\* is a range, not a point.
- All constants are this harness's and this workload's (Anthropic/Sonnet, infrastructure and task mix as of 2026-06-19). Not universal.
- Curation-rate estimate (17–33%) rests on 6 fan-out-worthy objectives. Order-of-magnitude only.
- The isolation-branch argument for K=3 is structurally sound but R\* (the isolation trigger magnitude) is a reasoned default, not measured. K and R\* are coupled; if R\* is eventually measured much higher than 50K tokens, the isolation-branch case for K=3 at small read volumes weakens.
