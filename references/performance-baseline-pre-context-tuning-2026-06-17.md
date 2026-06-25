# Performance Baseline — Pre-Context Tuning
**Captured:** 2026-06-17 ~22:00 EDT  
**State:** post-update v0.16.0, WebUI installed (hermes-webui systemd), skill audit complete  
**Method:** live probes, session-active system (load slightly elevated from this session)  
**Precedes:** 32B context 64k→32k rebuild + vision model context right-sizing  
**Compare to:** `performance-baseline-2026-06-17.md` (yesterday's idle baseline)

---

## Mac Studio (localadmins-mac-studio) — Inference Node

### Hardware (unchanged)
- Chip: Apple M2 Max
- RAM: 64GB unified memory
- VRAM cap: 57,344 MB (~56GB)
- Disk: 926GB (78GB used, 820GB free)

### Ollama Config (current, pre-tuning)
- `OLLAMA_NUM_PARALLEL=2`
- `OLLAMA_MAX_LOADED_MODELS=2`
- `OLLAMA_KEEP_ALIVE=30m`
- VRAM cap: `iogpu.wired_limit_mb=57344`

### Inference Benchmarks — qwen2.5-32b-64k (Q4_K_M)
*Role: delegation / cron / compression / curator*  
*Baked context: 65,536 tokens (RoPE-stretched beyond native 32k)*

| Run | Eval tok/s | Prompt tok/s | Load time |
|---|---|---|---|
| 1 (cold load) | 13.6 | 75.5 | 3.46s |
| 2 (warm) | 13.6 | 610.1 | 0.15s |
| 3 (warm) | 13.6 | 609.4 | 0.14s |

- **Warm eval: 13.6 t/s** (−1.4% vs yesterday idle baseline, within noise)
- **Warm prompt: ~610 t/s** (+12% vs yesterday — run-to-run variance)
- **Cold load: 3.46s**
- **KV reservation at 64k: ~32GB** (over-subscribed: 20GB weights + 32GB KV = 52GB solo; parallel=2 would need 64GB → spills/degrades)

### Inference Benchmarks — qwen2.5vl:7b (Q4_K_M)
*Role: vision tasks*  
*Baked context: 128,000 tokens (vastly oversized for vision use)*

| Run | Eval tok/s | Prompt tok/s | Load time |
|---|---|---|---|
| 1 (cold/warm) | 55.8 | 285.2 | 3.81s |
| 2 (warm) | 57.0 | 1,474.2 | 0.17s |
| 3 (warm) | 56.9 | 1,484.6 | 0.16s |

- **Warm eval: 57.0 t/s**
- **Warm prompt: ~1,480 t/s**
- **VRAM resident: 22.3GB @ 128k context** (~16GB of that is dead KV headroom never used)

### VRAM State (post-bench)
```
qwen2.5vl:7b    22.3GB  @ ctx=128,000   ← OVERSIZED
qwen2.5-32b     evicted (KEEP_ALIVE expired during bench gap)
TOTAL resident  22.3GB / 56GB cap
```

**Root problem:** Vision (22.3GB) + 32B weights (20GB) + 2-slot KV at 64k (64GB) = 106GB needed, 56GB available.  
Models thrash. 32B cannot stay warm alongside vision at current context sizes.

---

## Network (Tailscale mini → Studio)

| Metric | Value |
|---|---|
| TCP connect (cold/first) | 23.4ms |
| TCP connect (warm p50) | 3.4–3.8ms |
| API round-trip (tags) | 8.6ms |

---

## Mac Mini (andrew-Macmini) — Orchestration Node

*Note: load elevated vs yesterday baseline — this session running benches + WebUI.*

| Metric | Yesterday idle | Now (session active) |
|---|---|---|
| Load avg (1m/5m/15m) | 0.73/0.83/0.82 | 1.71/1.05/0.95 |
| RAM available | 25GB | 23.6GB |
| RAM used | 5.5GB / 31GB | 8.4GB / 31GB |
| Disk | 49GB / 458GB (12%) | 51GB / 458GB (12%) |
| Swap | 0B | 0B |

New memory consumers since yesterday baseline:
- `hermes-webui` systemd service: ~90MB RSS

---

## Delegation Config (current, pre-tuning)
- `max_concurrent_children: 8`
- `max_async_children: 3`
- `max_spawn_depth: 1`
- Subagent model: `qwen2.5-32b-64k` @ Studio
- Baked context: 65,536 tokens
- Effective GPU parallelism: **1** (nominal=2 but KV over-subscribed at 64k)

---

## What Changes After Tuning
1. `qwen2.5-32b-64k` rebuilt as `qwen2.5-32b-32k` (num_ctx 32768 — native ceiling)
   - KV/slot: 32GB → 16GB
   - Effective parallel slots at current NUM_PARALLEL=2: confirmed viable (20+32GB = 52GB ✓)
2. `qwen2.5vl:7b` Modelfile num_ctx lowered to 8192 (vision tasks never exceed ~4k)
   - VRAM: 22.3GB → est. ~7–8GB
   - Frees ~14–15GB, allows both models to co-reside comfortably
3. `max_concurrent_children`: 8 → 12 (pipeline buffer, subagents are off-GPU during tool phases)

## Post-Tuning Targets
| Metric | Current | Target |
|---|---|---|
| 32B effective parallel slots | 1 (degraded) | 2 (genuine) |
| Both models co-resident | No (thrash) | Yes (~44GB, 79% cap) |
| Concurrent subagents | 8 fan-out / 1 GPU slot | 12 fan-out / 2 GPU slots |
| 32B eval tok/s | 13.6 | 13.5–14.0 (flat, same weights) |
| 32B cold load | 3.46s | ~2.0–2.5s (smaller KV alloc) |
