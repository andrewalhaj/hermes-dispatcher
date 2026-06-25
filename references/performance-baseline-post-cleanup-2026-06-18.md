# Performance Baseline — Post-Cleanup (2026-06-18)
**Captured:** 2026-06-18 ~08:45 EDT
**Config:** OLLAMA_NUM_PARALLEL=1, MAX_LOADED_MODELS=1, delegation.model=qwen2.5-32b-64k
**Changes from prior session:** deleted qwen2.5-coder-14b-32k + qwen2.5-coder:14b; removed phantom qwen2.5-128k + stale qwen2.5-coder-14b-32k from custom_providers
**Supersedes:** performance-baseline-p1-2026-06-18.md
**Compare to:** performance-baseline-p1-2026-06-18.md (same P=1 config, pre-cleanup)

---

## Raw inference — qwen2.5-32b-64k (P=1, warm, from mini → Studio API)

| Metric | This run | P=1 baseline (2026-06-18 ~02:00) | Delta |
|---|---|---|---|
| Eval t/s (warm, run 2) | **13.5** | 13.5 | 0% |
| Eval t/s (warm, run 3) | **13.6** | 13.5 | +1% (noise) |
| Prompt t/s (warm, run 2) | **225** | 199 | +13% |
| Prompt t/s (warm, run 3) | **225** | 199 | +13% |
| Prompt t/s (run 1 / cold-or-firstwarm) | 23.1 | — | cache-miss on run 1 |
| Load time (warm) | 0.16s | 0.15s | noise |
| VRAM resident | **28.9 GB** | 28.9 GB | 0% |
| Disk used (models dir) | **63 GB** | 71 GB | **−8 GB** |

### Run log (raw)
| Run | Label | Eval t/s | Prompt t/s | Load | Tokens |
|---|---|---|---|---|---|
| 1 | cold-or-firstwarm | 13.5 | 23.1 | 0.16s | 120 |
| 2 | warm | 13.5 | 225.1 | 0.16s | 106 |
| 3 | warm | 13.6 | 225.0 | 0.16s | 65 |

---

## VRAM residency
- qwen2.5-32b-64k: 28.9 GB resident | ctx=32768 (baked num_ctx=65536, native=32768)
- Total: 28.9 GB / 56 GB cap (52%) | **27.1 GB headroom**
- Models on disk: qwen2.5-32b-64k (19 GB), qwen2.5:72b (47 GB)

---

## Key findings

**Eval t/s is unchanged** — 13.5–13.6 t/s. Expected: same weights, same quant, same eval speed.

**Prompt t/s improved +13%** (199 → 225 t/s). Most likely cause: the coder models were recently
loaded (modified 5 hours ago) and may have been competing for VRAM / Metal shader residency.
With them gone, the 32B had cleaner exclusive access. Could also be run-to-run noise (~10–15%
is normal), but the direction is consistent across two warm runs.

**Prompt run 1 (23.1 t/s)** — the first call hit a cache miss; the prior prompt differed
enough to invalidate the prefix. Runs 2–3 show the 225 t/s warm-cache figure.

**27.1 GB headroom** — enough to co-load a small vision model (qwen2.5vl:7b ~6–8 GB)
alongside the 32B if needed, with room to spare.

---

## Studio model inventory (clean state)
| Model | Disk | VRAM (P=1) | Delegation-viable |
|---|---|---|---|
| qwen2.5-32b-64k | 19 GB | 28.9 GB | ✅ YES (current target) |
| qwen2.5:72b | 47 GB | ~45–50 GB (solo only) | ✅ YES (too slow, solo only) |
| ~~qwen2.5-coder-14b-32k~~ | deleted | — | ❌ (text tool-calls) |
| ~~qwen2.5-coder:14b~~ | deleted | — | ❌ (text tool-calls) |
