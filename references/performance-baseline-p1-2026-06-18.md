# Performance Baseline — P=1 (Studio Delegation)
**Captured:** 2026-06-18 ~02:00 EDT
**Config:** OLLAMA_NUM_PARALLEL=1, MAX_LOADED_MODELS=1, delegation.model=qwen2.5-32b-64k
**Supersedes for delegation:** performance-baseline-p4-final-2026-06-17.md
**Compare to:** performance-baseline-2026-06-17.md (original idle baseline)

---

## Raw single-stream inference (warm, P=1) — qwen2.5-32b-64k

| Metric | Value | vs 2026-06-17 baseline |
|---|---|---|
| Eval t/s (warm) | 13.5 | 13.8 (−2%, noise — same weights) |
| Prompt t/s (warm) | 199 | 546* (baseline was cache-inflated) |
| Load (warm) | 0.15s | 0.2s |
| VRAM resident | **28.9GB** | 37.5GB (P=2) / 54.4GB (P=4) |

*The 546 t/s baseline prompt figure was measured immediately post-warmup with a near-identical
prompt = cache hit. 199 t/s is the honest cold-ingest rate. Eval t/s (the real generation
work) is unchanged → generation speed is identical; only the cache-inflated metric "regressed."

## VRAM: the unambiguous P=1 win
- P=4: 54.4GB resident (4 KV slots)
- P=2: 37.5GB
- **P=1: 28.9GB** — frees ~25GB vs P=4. Headroom for bigger context or the 72B.

## End-to-end delegation (real delegate_task, P=1)

| Scenario | Time |
|---|---|
| Clean sequential, no interleaving (earlier) | 136 → 104 → 110 → 106s |
| Cold (gcd, this run) | 105s |
| Second call WITH aux interleaving (lcm) | 171s ← prefix evicted |
| Original baseline "round-trip zero-tool" | 156s |

## ⚠️ KEY FINDING: P=1 single-slot contention
At P=1 there is ONE Ollama slot. Delegation subagents AND any Studio-routed aux call
(curator, etc.) share it. Studio logs (this session) showed an aux call with sim_best=0.894
landing in slot 0 BETWEEN two delegations and EVICTING the delegation prefix → the next
delegation fell back to the ~3,400-token edit-heavy floor and ran 171s instead of ~30s.

**Implication:** P=1's prefix-cache win (~30s/task) only materializes when delegation has the
slot to itself. Aux traffic sharing the Studio breaks it. To realize the cache benefit,
delegation should not share its slot with other Studio-routed roles. (See aux-routing analysis.)

## Decision logged: P=1 chosen
Rationale: delegation pattern is overwhelmingly sequential; prefix-cache win is large in quiet
sessions; VRAM reclaim is real; P=2's parallelism only pays for simultaneous batches (rare).
Trade-off accepted: no true concurrency (sequential tasks queue), and cache benefit is fragile
under aux contention (addressed separately).
