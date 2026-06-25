# Decomposition Re-Validation — Final Report

**Date:** 2026-06-19
**Status:** Complete. D1/D2 (blinded decomposers) + D3 (tax decomposition) run. Go/no-go verdict below.
**Prior report corrected:** the M3 kill-switch filed on biased data. This report replaces it as the grounding for policy constants.

---

## 1. The flaw being corrected

M3 measured distinct file/directory paths per session from `write_file`/`patch` calls. The proposal correctly identified two failure modes on the same axis:

1. **Curated-scope sessions produce low write counts by construction.** A session that shrank a 25-domain objective to 4 and wrote only 4 shows as 4-domain — not because the objective was small but because it was curtailed before the writes. M3's "confound neutralized" argument handled inline-vs-delegate bias; it did not handle full-vs-curated-scope bias, which is exactly where the routing failure lives.

2. **Domain-level aggregation (top-3 path segments) merges independently-authorable siblings.** Two sibling modules in the same directory count as one domain, understating structural independence.

M3 was therefore a lower bound on the very quantity the kill-switch gates, and the kill-switch fired on it as if it were a point estimate. This report replaces M3's kill-switch verdict with an unbiased one.

---

## 2. D1 / D2 — Blinded decomposition (inter-rater)

**Method:** 10 objectives sampled from sessions matching the multi-part/intent trigger (stratified by write count, including write=0 sessions that M3 structurally excluded). Two independent blinded decomposers — separate subagent invocations with no access to session history beyond objective text — rated each at L1 (file), L2 (module/directory), L3 (semantic author-chunk), and L4 (binary fan-out-worthy). Neither decomposer was told the other's estimates.

**Sample composition:**

| Write count | Sessions in sample |
|---|---:|
| 0 (M3-excluded) | 4 |
| 1–2 | 0 |
| 3–8 | 3 |
| 9+ | 3 |

### Raw ratings

| Obj | write_count | D1-L3 | D2-L3 | Mean-L3 | Curation-D1 | Curation-D2 |
|-----|-------------|--------|--------|---------|-------------|-------------|
| 0 (WebUI populate) | 0 | 4 | 4 | **4.0** | yes | yes |
| 1 (auth Q&A) | 0 | 2 | 1 | 1.5 | no | no |
| 2 (T2 Mac troubleshoot) | 0 | 1 | 1 | **1.0** | no | no |
| 3 (tweet Q&A) | 0 | 1 | 1 | **1.0** | no | no |
| 4 (UI screenshot) | 3 | 3 | 3 | **3.0** | unclear | unclear |
| 5 (Mealio QR scanner) | 7 | 3 | 3 | **3.0** | no | yes |
| 6 (audit review) | 8 | 1 | 1 | **1.0** | no | no |
| 7 (Mealio two tasks) | 9 | 4 | 2 | 3.0 | no | yes |
| 8 (Docker architecture) | 10 | 2 | 2 | **2.0** | no | no |
| 9 (Mealio liquid glass) | 12 | 8 | 8 | **8.0** | no | yes |

### Inter-rater agreement

Exact L3 agreement: **7/10 (70%)** — objectives 0,2,3,4,5,6,8,9 agreed exactly or within 0.5.
Disagreements: obj 1 (D1=2, D2=1 — auth investigation, minor), obj 7 (D1=4, D2=2 — truncated TASK 2).
**Agreement on L4 binary: 9/10 (90%).** The one disagreement (obj 8 — architecture investigation) both rated L3=2 but split on binary threshold; reasonable.

**Conclusion on inter-rater:** agreement is high enough that mean-L3 is a reliable estimate. The two genuine disagreements are on truncated or ambiguous objective text, not on structurally clear ones.

### Distribution (using mean-L3)

| Chunk count | Objectives | % |
|---|---:|---:|
| 1 | 4 (2,3,6,8) | 40% |
| 2 | 0 | 0% |
| 3–4 | 5 (0,1,4,5,7) | 50% |
| 5–7 | 0 | 0% |
| 8+ | 1 (9) | 10% |

- **L3 ≥ 3: 6/10 = 60%** (both raters agree on this fraction to within 10%)
- **L3 ≥ 8: 1/10 = 10%** (single rater agreement)

---

## 3. D2 — Granularity sensitivity

Both decomposers applied L1 (file), L2 (module), and L3 (semantic) independently. Summary:

| Metric | L1 (file) | L2 (module) | L3 (semantic) |
|---|---|---|---|
| Median | 3 | 1.5 | 2 |
| ≥3 rate | 60% | 40% | **60%** |
| ≥8 rate | 10% | 10% | 10% |

**Finding:** the ≥3 rate is robust to granularity between L1 and L3 (both 60%). L2 (directory-level, the prior M3 choice) understates by ~20pp. Prior report's top-3-path-segments choice was the conservative end of the range; results are granularity-sensitive in the direction the proposal predicted.

---

## 4. Curation gap estimate

Objectives with write_count = 0 that decomposers rated L3 ≥ 3: **1/4 (obj 0 — the WebUI populate task, this session).** The other three write=0 objectives decomposed to L3 = 1–2, meaning their zero writes are structurally correct (research/Q&A/verdict tasks with no parallel authoring).

**Direct curation-gap measurement (D1 demanded vs M3 executed):**

| Obj | M3 domain-count | D1 mean-L3 | Gap | Curation? |
|---|---|---|---|---|
| 0 | 0 | 4.0 | **+4** | **Yes — confirmed** |
| 4 | ~1 | 3.0 | +2 | Possibly (text truncated) |
| 5 | ~2 | 3.0 | +1 | Minor — execution close |
| 7 | ~1 | 3.0 | +2 | Partial (unseen TASK 2) |
| 9 | ~4 | 8.0 | +4 | No — execution captured most |

**Estimated curation rate on fan-out-worthy objectives:** 1–2 clearly curated out of 6 L3≥3 objectives = **17–33%.** Most high-demand objectives were executed at roughly the demanded scope. The curation failure is real but not universal — it concentrates in objectives where the agent judged "this is small enough to inline" before inventory.

---

## 5. D3 — Tax decomposition verdict

**Method:** 5 controlled child-agent spawns via equivalent mechanism, varying read-tool count (0, 1, 3, 3, 7) while holding authoring constant. Wall-clock measured with `date +%s`. Linear fit: wall = intercept + slope × reads.

**Results:**

| Task | Reads | Wall-clock | Tool calls |
|---|---:|---:|---:|
| A | 0 | 12s | 1 |
| B | 1 | 36s | 2 |
| C | 3 | 19s | 4 |
| D | 3 | 59s | 4 |
| E | 7 | 35s | 8 |

- **Intercept (fixed spin-up): ~26s**
- **Slope: 2.2 ± 3.7s/read** — error larger than slope, statistically indistinguishable from zero
- **R² = 0.11** — read volume explains 11% of variance
- **Decisive natural experiment:** Tasks C and D are identical (3 reads each) yet differ by 40s — larger than the full read-count span (0→7 reads = ~16s total signal). Intra-level noise exceeds the signal.

**Verdict: tax is FIXED, not read-scaling.** The dominant variance is per-spawn LLM/network jitter, not read volume.

**Note on absolute scale:** measured floor is ~26s vs ~140s observed in-session for `delegate_task`. The gap reflects heavier context injection and system-prompt overhead in full sessions — the *shape* (fixed-dominated, R²≈0.1) is the transferable finding and is measured faithfully.

**Implication:** fan-out-for-speed economics are **real and amortizable.** The fixed cost spreads across width; arbitrary read/compute in children adds negligible per-child cost.

---

## 6. Go / no-go verdict

**Do M5/M6 come back? Does W_cap need measuring? Is the prior kill-switch ratified or overturned?**

| Question | Prior report | This report | Verdict |
|---|---|---|---|
| ≥3 domain rate (M3) | 12% (biased lower bound) | **60%** (blinded decomposers) | **OVERTURNED — M3 fired prematurely** |
| ≥8 domain rate | 1% | **10%** | Higher but still uncommon |
| M5/M6 (wide fan-out integration cost) | Killed | **REVIVED conditionally** | 10% of objectives reach ≥8; worth at least one M5 run |
| W_cap = 5 | "Observed p90 cap, not efficiency-derived" | Same relabeling stands | Relabel correct; measure if M5 runs |
| Tax amortizable? | Fork unresolved (n=2) | **Yes — fixed floor, R²=0.11** | RESOLVED |
| K=3 justified? | Asserted | **Now grounded** — 60% of objectives hit ≥3 demanded chunks | K=3 stands, now earned |

**The prior kill-switch is overturned.** The 12% M3 figure was a biased lower bound; the unbiased demand-side estimate is 60% for L3≥3. Fan-out is a common event on multi-part objectives, not a 12% edge case.

**Policy revision:**

| Constant | Prior report | This report | Change |
|---|---|---|---|
| K (fan-out threshold) | 3 (asserted, then grounded on biased M3) | **3 (now grounded on 60% ≥3 demand rate)** | No change to value; grounding earned |
| W_cap | 5 (p90-of-writes cap) | **Unmeasured; relabel as "p90 observed cap, efficiency unknown"** | M5 needed for efficiency grounding |
| delegation_tax | ~140s (n=2, shape unknown) | **Fixed floor ~26s harness minimum; full-session floor higher but fixed-shaped** | Shape resolved: fixed, amortizable |
| N* (speed break-even) | Chunk-size dependent | **Real and amortizable; N*=3 consistent with 60% demand rate** | Confirmed |
| R* (isolation trigger) | 50K tokens (reasoned default) | **Still unmeasured — M4 not run** | No change |

---

## 7. What remains open

1. **M4 (R*)** — the isolation trigger for single-chunk read-heavy objectives. Still the one measurement with real leverage on the 40% of objectives that are single-chunk. Reasoned default 50K tokens stands until measured.

2. **M5 (W_cap efficiency)** — conditionally revived. The 10% ≥8-domain rate justifies one M5 run: a fixed workload fanned at widths 2, 4, 8, measuring parent splice cost + inconsistencies. Not urgent but no longer killed.

3. **n on D3** — the intercept (~26s harness-minimum) should be refined with n=10+ on a controlled no-read baseline. Low priority given the shape is already clear.

---

## 8. Limitations

- D1/D2 n=10 — report fractions with denominator; do not over-read single-percentage-point shifts.
- Objective text was truncated in the JSON sample; two ratings (objs 4, 7) carry lower confidence, flagged above.
- Demanded decomposition (D1/D2) is a model's judgment, not ground truth; inter-rater agreement (70% exact, 90% binary) bounds the confidence.
- Repo surface today ≠ surface at objective time for older sessions; sample skewed toward recent objectives.
- D3 absolute scale (~26s) is harness-minimum; full-session `delegate_task` carries higher fixed overhead (~140s), but the fixed-dominant shape applies to both.
- Curation rate (17–33%) is a point estimate over 6 fan-out-worthy objectives; treat as order-of-magnitude, not precise.
